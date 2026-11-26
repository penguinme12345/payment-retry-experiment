"""Synthetic data generator for the RetryLab experiment (PRD-A).

Everything is drawn from a single seeded ``numpy.random.Generator`` in a fixed order, so the
same config produces byte-identical Parquet files. Timestamps are handled internally as int64
microseconds since the Unix epoch (UTC, naive) and converted to ``timestamp[us]`` on write.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from retrylab.sim.config import DECLINE_CODES, SimConfig, load_config
from retrylab.sim.schemas import SCHEMAS

# --------------------------------------------------------------------------------------------
# Constants (contract C2) and behavioural parameters of the generative model
# --------------------------------------------------------------------------------------------
EXPERIMENT_ID = "retry_timing_v1"
VARIANTS = ("control", "treatment")
PLAN_PRICE = {"basic": 9.00, "pro": 29.00, "business": 99.00}
PAYDAYS = (1, 15, 28)

SEC = 1_000_000
MIN = 60 * SEC
HOUR = 60 * MIN
DAY = 24 * HOUR


def _us(ts: str) -> int:
    return int(np.datetime64(ts, "us").astype(np.int64))


WINDOW_START = _us("2026-03-01T00:00:00")
WINDOW_SECONDS = 31 * 86_400  # through 2026-03-31 23:59:59
PRE_START_MONTH = np.datetime64("2025-03", "M")
SIGNUP_START = _us("2023-03-01T00:00:00")
SIGNUP_END = _us("2025-03-01T00:00:00")  # contract C3: signup_at before 2025-03-01
BACKGROUND_TICKET_START = _us("2025-03-01T00:00:00")
BACKGROUND_TICKET_END = _us("2026-05-01T00:00:00")

CONTROL_RETRY_DAYS = (1, 3, 5, 7)
MAX_RETRIES = 4
RETRY_WINDOW = 7 * DAY
MIN_RETRY_GAP = 1 * HOUR  # earliest a smart retry may follow the initial failure

# Pre-period: initial-attempt failure (logit scale) and per-retry success, both driven by the
# latent stability. Mean initial failure is ~6.5%; tuned so corr(pre_failed_attempt_rate,
# is_recovered) lands near -0.28.
PRE_FAIL_INTERCEPT = -3.1
PRE_FAIL_STABILITY_COEF = -1.0
PRE_RETRY_INTERCEPT = 0.3
PRE_RETRY_STABILITY_COEF = 0.6
PREFERRED_HOUR_SHARE = 0.6  # share of pre-period invoices billed at the customer's usual hour

# Experiment recovery: logit-scale stability effect (centred per cell, see _centred_probs).
RECOVERY_STABILITY_COEF = 1.8
# Which retry (1-4) succeeds, given recovery. Treatment recovers earlier on average.
SUCCESS_RETRY_DIST = {
    "control": (0.40, 0.30, 0.20, 0.10),
    "treatment": (0.55, 0.25, 0.13, 0.07),
}
PREPAID_INSUFFICIENT_FUNDS_MULTIPLIER = 2.0
EXPIRED_CARD_MIN_TENURE = 183 * DAY  # no expired_card for customers signed up < ~6 months ago
BACKGROUND_TICKETS_PER_CUSTOMER = 0.15
SRM_DROP_SHARE = 0.03


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _logit(p: float) -> float:
    return float(np.log(p / (1.0 - p)))


def _choice(rng: np.random.Generator, mix: dict[str, float], size: int) -> np.ndarray:
    keys = np.array(list(mix.keys()), dtype=object)
    probs = np.array(list(mix.values()), dtype=float)
    return keys[rng.choice(len(keys), size=size, p=probs / probs.sum())]


def _centred_probs(stability: np.ndarray, target: float, coef: float) -> np.ndarray:
    """Per-unit probabilities ``sigmoid(logit(target) + c + coef*stability)``.

    ``c`` is solved by bisection so that the mean probability over this group equals ``target``
    exactly, which keeps the population rate on the configured value while letting stability
    drive individual differences.
    """
    if stability.size == 0:
        return np.empty(0)
    if target <= 0.0 or target >= 1.0:
        return np.full(stability.shape, target)
    base = _logit(target) + coef * stability
    lo, hi = -20.0, 20.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _sigmoid(base + mid).mean() < target:
            lo = mid
        else:
            hi = mid
    return _sigmoid(base + (lo + hi) / 2.0)


@dataclass
class _Invoices:
    """Invoice-level arrays plus the per-attempt schedule needed to expand attempts."""

    cust: np.ndarray  # customer index
    created: np.ndarray  # int64 us
    is_exp: np.ndarray  # bool
    n_attempts: np.ndarray  # 1..5
    success_attempt: np.ndarray  # attempt_number that succeeded, -1 if none
    decline: np.ndarray  # decline code used for failed attempts (object, may be None)
    times: np.ndarray  # (n, 5) int64 us: attempt times by attempt_number


def _pre_period(
    cfg: SimConfig,
    rng: np.random.Generator,
    stability: np.ndarray,
    billing_day: np.ndarray,
    preferred_hour: np.ndarray,
) -> _Invoices:
    n = stability.size
    months = cfg.pre_period_months
    cust = np.repeat(np.arange(n), months)
    month_idx = np.tile(np.arange(months), n)
    month_start = (PRE_START_MONTH + month_idx).astype("datetime64[us]").astype(np.int64)

    k = cust.size
    at_pref = rng.random(k) < PREFERRED_HOUR_SHARE
    hour = np.where(at_pref, preferred_hour[cust], rng.integers(0, 24, size=k))
    seconds = rng.integers(0, 3600, size=k)
    created = month_start + (billing_day[cust] - 1) * DAY + hour * HOUR + seconds * SEC

    stab = stability[cust]
    p_fail = _sigmoid(PRE_FAIL_INTERCEPT + PRE_FAIL_STABILITY_COEF * stab)
    fail0 = rng.random(k) < p_fail
    p_retry = _sigmoid(PRE_RETRY_INTERCEPT + PRE_RETRY_STABILITY_COEF * stab)
    retry_ok = rng.random((k, MAX_RETRIES)) < p_retry[:, None]
    any_ok = retry_ok.any(axis=1)
    first_ok = np.where(any_ok, retry_ok.argmax(axis=1) + 1, -1)

    success_attempt = np.where(fail0, first_ok, 0)
    n_attempts = np.where(fail0, np.where(any_ok, first_ok + 1, MAX_RETRIES + 1), 1)
    decline = np.where(fail0, _choice(rng, cfg.decline_mix, k), None)

    offsets = np.array((0,) + CONTROL_RETRY_DAYS, dtype=np.int64) * DAY
    times = created[:, None] + offsets[None, :]
    return _Invoices(cust, created, np.zeros(k, bool), n_attempts, success_attempt, decline, times)


def _modal_success_hour(pre: _Invoices, n: int) -> np.ndarray:
    """Most common hour-of-day of each customer's successful pre-period attempts (-1 if none)."""
    ok = pre.success_attempt >= 0
    rows = np.arange(pre.cust.size)[ok]
    t = pre.times[rows, pre.success_attempt[ok]]
    hours = (t % DAY) // HOUR
    counts = np.bincount(pre.cust[ok] * 24 + hours, minlength=n * 24).reshape(n, 24)
    modal = counts.argmax(axis=1)
    return np.where(counts.sum(axis=1) > 0, modal, -1)


def _next_payday_slot(t0: int, payday: int, hour: int) -> int | None:
    """First retry slot at ``hour`` on a payday date inside the retry window, or None."""
    day0 = np.datetime64(t0, "us").astype("datetime64[D]")
    month0 = day0.astype("datetime64[M]")
    for m in (0, 1):
        month = month0 + np.timedelta64(m, "M")
        pay_date = month.astype("datetime64[D]") + np.timedelta64(payday - 1, "D")
        slot = int(pay_date.astype("datetime64[us]").astype(np.int64)) + hour * HOUR
        if t0 + MIN_RETRY_GAP <= slot <= t0 + RETRY_WINDOW:
            return slot
    return None


def _treatment_schedule(t0: int, payday: int | None, hour: int, minute_offset: int) -> list[int]:
    """Smart retry times: payday-aware, else spread over the customer's usual success hour."""
    day0 = t0 - t0 % DAY
    candidates = [
        day0 + d * DAY + hour * HOUR + minute_offset
        for d in range(8)
        if t0 + MIN_RETRY_GAP <= day0 + d * DAY + hour * HOUR + minute_offset <= t0 + RETRY_WINDOW
    ]
    chosen: list[int] = []
    if payday is not None:
        slot = _next_payday_slot(t0, payday, hour)
        if slot is not None:
            slot += minute_offset
            if slot > t0 + RETRY_WINDOW:
                slot -= minute_offset
            chosen.append(slot)
            candidates = [c for c in candidates if c // DAY != slot // DAY]
    need = MAX_RETRIES - len(chosen)
    idx = np.round(np.linspace(0, len(candidates) - 1, need)).astype(int)
    chosen.extend(candidates[i] for i in idx)
    return sorted(chosen)


def _experiment(
    cfg: SimConfig,
    rng: np.random.Generator,
    stability: np.ndarray,
    signup: np.ndarray,
    funding: np.ndarray,
    payday: np.ndarray,
    modal_hour: np.ndarray,
) -> tuple[_Invoices, np.ndarray, np.ndarray]:
    n = stability.size
    truth = cfg.truth
    t0 = WINDOW_START + rng.integers(0, WINDOW_SECONDS, size=n) * SEC

    # Initial decline code: prepaid skews to insufficient_funds; no expired_card for new signups.
    codes = np.array(DECLINE_CODES, dtype=object)
    base_w = np.array([cfg.decline_mix[c] for c in DECLINE_CODES])
    prepaid_w = base_w.copy()
    prepaid_w[0] *= PREPAID_INSUFFICIENT_FUNDS_MULTIPLIER
    new_w = base_w.copy()
    new_w[1] = 0.0
    weights = np.where((funding == "prepaid")[:, None], prepaid_w, base_w)
    is_new = (t0 - signup) < EXPIRED_CARD_MIN_TENURE
    weights = np.where(is_new[:, None], np.where(new_w > 0, weights, 0.0), weights)
    cum = np.cumsum(weights / weights.sum(axis=1, keepdims=True), axis=1)
    decline = codes[(rng.random(n)[:, None] > cum).sum(axis=1).clip(max=len(codes) - 1)]

    treat = rng.random(n) < 0.5
    variant = np.where(treat, "treatment", "control").astype(object)

    # Recovery probability per cell, centred so each cell's mean equals the configured rate.
    payday_known = payday > 0
    p_rec = np.empty(n)
    for code in DECLINE_CODES:
        base = truth.baseline_recovery[code]
        lift = truth.treatment_lift_abs[code]
        cells = [(~treat, base)]
        if code == "insufficient_funds":
            extra = truth.payday_known_extra_lift_abs
            cells += [
                (treat & payday_known, base + lift + extra),
                (treat & ~payday_known, base + lift),
            ]
        else:
            cells += [(treat, base + lift)]
        for mask, target in cells:
            m = mask & (decline == code)
            p_rec[m] = _centred_probs(stability[m], target, RECOVERY_STABILITY_COEF)
    recovered = rng.random(n) < p_rec

    success_retry = np.empty(n, dtype=np.int64)
    for v, is_t in (("control", False), ("treatment", True)):
        m = treat == is_t
        success_retry[m] = rng.choice(np.arange(1, 5), size=int(m.sum()), p=SUCCESS_RETRY_DIST[v])
    success_attempt = np.where(recovered, success_retry, -1)
    n_attempts = np.where(recovered, success_retry + 1, MAX_RETRIES + 1)

    minute_offset = rng.integers(0, 3600, size=n) * SEC
    hour = np.where(modal_hour >= 0, modal_hour, (t0 % DAY) // HOUR)
    times = np.empty((n, MAX_RETRIES + 1), dtype=np.int64)
    times[:, 0] = t0
    control_offsets = np.array(CONTROL_RETRY_DAYS, dtype=np.int64) * DAY
    times[~treat, 1:] = t0[~treat, None] + control_offsets[None, :]
    for i in np.flatnonzero(treat):
        pd_i = int(payday[i]) if payday[i] > 0 else None
        times[i, 1:] = _treatment_schedule(int(t0[i]), pd_i, int(hour[i]), int(minute_offset[i]))

    inv = _Invoices(
        cust=np.arange(n),
        created=t0,
        is_exp=np.ones(n, bool),
        n_attempts=n_attempts,
        success_attempt=success_attempt,
        decline=decline,
        times=times,
    )
    return inv, variant, recovered


def _expand_attempts(inv: _Invoices) -> dict[str, np.ndarray]:
    inv_rep = np.repeat(np.arange(inv.cust.size), inv.n_attempts)
    starts = np.repeat(np.cumsum(inv.n_attempts) - inv.n_attempts, inv.n_attempts)
    att_num = np.arange(inv_rep.size) - starts
    succeeded = att_num == inv.success_attempt[inv_rep]
    return {
        "invoice": inv_rep,
        "attempt_number": att_num,
        "attempted_at": inv.times[inv_rep, att_num],
        "succeeded": succeeded,
        "decline_code": np.where(succeeded, None, inv.decline[inv_rep]),
    }


def _ids(prefix: str, n: int, width: int, start: int = 1) -> np.ndarray:
    return np.array([f"{prefix}{i:0{width}d}" for i in range(start, start + n)], dtype=object)


def _ts(values: np.ndarray) -> pa.Array:
    return pa.array(values.astype(np.int64), type=pa.int64()).cast(pa.timestamp("us"))


def simulate(cfg: SimConfig) -> dict[str, pa.Table]:
    """Run the generative model and return the six raw tables as PyArrow tables."""
    rng = np.random.default_rng(cfg.seed)
    n = cfg.n_customers

    # 1. Customers
    country = _choice(rng, cfg.country_mix, n)
    plan = _choice(rng, cfg.plan_mix, n)
    funding = _choice(rng, cfg.funding_mix, n)
    brand = _choice(rng, cfg.brand_mix, n)
    signup = SIGNUP_START + rng.integers(0, (SIGNUP_END - SIGNUP_START) // SEC, size=n) * SEC
    payday_known = rng.random(n) < cfg.payday_known_rate
    payday = np.where(payday_known, rng.choice(PAYDAYS, size=n), 0)
    stability = rng.standard_normal(n)
    billing_day = rng.integers(1, 29, size=n)
    preferred_hour = rng.integers(6, 23, size=n)
    price = np.array([PLAN_PRICE[p] for p in plan])

    # 2. Pre-period history, 3-5. experiment invoice, assignment, recovery, retry timing
    pre = _pre_period(cfg, rng, stability, billing_day, preferred_hour)
    modal_hour = _modal_success_hour(pre, n)
    exp, variant, recovered = _experiment(cfg, rng, stability, signup, funding, payday, modal_hour)
    t0 = exp.created
    treat = variant == "treatment"

    # 7. Tickets and churn
    truth = cfg.truth
    p_ticket = np.where(
        treat, truth.billing_ticket_rate["treatment"], truth.billing_ticket_rate["control"]
    )
    billing = rng.random(n) < p_ticket
    billing_at = t0 + rng.integers(0, 14 * 86_400, size=n) * SEC
    n_other = rng.poisson(BACKGROUND_TICKETS_PER_CUSTOMER, size=n)
    other_cust = np.repeat(np.arange(n), n_other)
    other_span = (BACKGROUND_TICKET_END - BACKGROUND_TICKET_START) // SEC
    other_at = BACKGROUND_TICKET_START + rng.integers(0, other_span, size=other_cust.size) * SEC

    invol = ~recovered & (rng.random(n) < truth.involuntary_churn_given_unrecovered)
    invol_at = t0 + RETRY_WINDOW + rng.integers(1, 23 * 86_400, size=n) * SEC
    vol = ~invol & (rng.random(n) < truth.voluntary_churn_30d)
    vol_at = t0 + rng.integers(0, 30 * 86_400, size=n) * SEC

    # 8. SRM toggle: drop a share of treatment customers after assignment (drawn last so the
    # rest of the dataset is identical with and without it).
    keep = np.ones(n, bool)
    if cfg.inject_srm:
        treat_idx = np.flatnonzero(treat)
        n_drop = int(round(SRM_DROP_SHARE * treat_idx.size))
        keep[rng.choice(treat_idx, size=n_drop, replace=False)] = False

    cust_ids = _ids("cus_", n, 6)

    # ---- raw_customers / raw_assignments
    k = np.flatnonzero(keep)
    tables: dict[str, dict[str, pa.Array]] = {}
    tables["raw_customers"] = {
        "customer_id": pa.array(cust_ids[k], pa.string()),
        "signup_at": _ts(signup[k]),
        "country": pa.array(country[k], pa.string()),
        "plan_tier": pa.array(plan[k], pa.string()),
        "monthly_price_usd": pa.array(price[k], pa.float64()),
        "card_brand": pa.array(brand[k], pa.string()),
        "card_funding": pa.array(funding[k], pa.string()),
        "payday_day_of_month": pa.array(payday[k], pa.int32(), mask=~payday_known[k]),
    }
    tables["raw_assignments"] = {
        "customer_id": pa.array(cust_ids[k], pa.string()),
        "experiment_id": pa.array([EXPERIMENT_ID] * k.size, pa.string()),
        "variant": pa.array(variant[k], pa.string()),
        "assigned_at": _ts(t0[k]),
    }

    # ---- raw_invoices / raw_payment_attempts: combine, filter, order, assign ids
    all_inv = _Invoices(
        cust=np.concatenate([pre.cust, exp.cust]),
        created=np.concatenate([pre.created, exp.created]),
        is_exp=np.concatenate([pre.is_exp, exp.is_exp]),
        n_attempts=np.concatenate([pre.n_attempts, exp.n_attempts]),
        success_attempt=np.concatenate([pre.success_attempt, exp.success_attempt]),
        decline=np.concatenate([pre.decline, exp.decline]),
        times=np.concatenate([pre.times, exp.times]),
    )
    order = np.lexsort((all_inv.cust, all_inv.created))
    order = order[keep[all_inv.cust[order]]]
    inv = _Invoices(*(getattr(all_inv, f)[order] for f in _Invoices.__dataclass_fields__))
    inv_ids = _ids("in_", inv.cust.size, 7)
    tables["raw_invoices"] = {
        "invoice_id": pa.array(inv_ids, pa.string()),
        "customer_id": pa.array(cust_ids[inv.cust], pa.string()),
        "amount_usd": pa.array(price[inv.cust], pa.float64()),
        "created_at": _ts(inv.created),
        "is_experiment_invoice": pa.array(inv.is_exp, pa.bool_()),
        "status": pa.array(
            np.where(inv.success_attempt >= 0, "paid", "uncollectible"), pa.string()
        ),
    }
    att = _expand_attempts(inv)
    tables["raw_payment_attempts"] = {
        "attempt_id": pa.array(_ids("py_", att["invoice"].size, 8), pa.string()),
        "invoice_id": pa.array(inv_ids[att["invoice"]], pa.string()),
        "attempt_number": pa.array(att["attempt_number"], pa.int32()),
        "attempted_at": _ts(att["attempted_at"]),
        "outcome": pa.array(np.where(att["succeeded"], "succeeded", "failed"), pa.string()),
        "decline_code": pa.array(att["decline_code"], pa.string()),
    }

    # ---- raw_support_tickets
    t_cust = np.concatenate([np.flatnonzero(billing), other_cust])
    t_at = np.concatenate([billing_at[billing], other_at])
    t_cat = np.array(
        ["billing_complaint"] * int(billing.sum()) + ["other"] * other_cust.size, object
    )
    t_keep = keep[t_cust]
    t_cust, t_at, t_cat = t_cust[t_keep], t_at[t_keep], t_cat[t_keep]
    t_order = np.lexsort((t_cust, t_at))
    tables["raw_support_tickets"] = {
        "ticket_id": pa.array(_ids("tkt_", t_order.size, 7), pa.string()),
        "customer_id": pa.array(cust_ids[t_cust[t_order]], pa.string()),
        "created_at": _ts(t_at[t_order]),
        "category": pa.array(t_cat[t_order], pa.string()),
    }

    # ---- raw_subscription_events
    e_cust = np.concatenate([np.flatnonzero(invol), np.flatnonzero(vol)])
    e_at = np.concatenate([invol_at[invol], vol_at[vol]])
    e_type = np.array(
        ["churned_involuntary"] * int(invol.sum()) + ["churned_voluntary"] * int(vol.sum()), object
    )
    e_keep = keep[e_cust]
    e_cust, e_at, e_type = e_cust[e_keep], e_at[e_keep], e_type[e_keep]
    e_order = np.lexsort((e_cust, e_at))
    tables["raw_subscription_events"] = {
        "customer_id": pa.array(cust_ids[e_cust[e_order]], pa.string()),
        "event_type": pa.array(e_type[e_order], pa.string()),
        "event_at": _ts(e_at[e_order]),
    }

    out: dict[str, pa.Table] = {}
    for name, cols in tables.items():
        schema = SCHEMAS[name]
        out[name] = pa.Table.from_arrays([cols[f.name].cast(f.type) for f in schema], schema=schema)
    return out


def generate(config_path: Path, out_dir: Path) -> dict[str, int]:
    """Generate the six raw Parquet tables from ``config_path`` into ``out_dir``.

    Returns the row count per table.
    """
    cfg = load_config(Path(config_path))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, table in simulate(cfg).items():
        pq.write_table(table, out_dir / f"{name}.parquet", compression="snappy")
        counts[name] = table.num_rows
    return counts
