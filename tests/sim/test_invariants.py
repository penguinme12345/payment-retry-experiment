"""Contract C3 invariants and structural checks on a 2,000-customer run."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DAY = pd.Timedelta(days=1)
WINDOW_START = pd.Timestamp("2026-03-01 00:00:00")
WINDOW_END = pd.Timestamp("2026-03-31 23:59:59")
PRICES = {"basic": 9.0, "pro": 29.0, "business": 99.0}


def _attempts(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    inv = t["raw_invoices"][["invoice_id", "customer_id", "is_experiment_invoice", "status"]]
    return t["raw_payment_attempts"].merge(inv, on="invoice_id", validate="many_to_one")


def test_one_customer_row_and_assignment_each(small: dict[str, pd.DataFrame]) -> None:
    cus, asg = small["raw_customers"], small["raw_assignments"]
    assert len(cus) == 2000 and cus.customer_id.is_unique
    assert set(asg.customer_id) == set(cus.customer_id) and asg.customer_id.is_unique
    assert (asg.experiment_id == "retry_timing_v1").all()
    assert set(asg.variant) == {"control", "treatment"}


def test_customer_attributes(small: dict[str, pd.DataFrame]) -> None:
    cus = small["raw_customers"]
    assert (cus.signup_at < pd.Timestamp("2025-03-01")).all()
    assert set(cus.country) <= {"US", "CA", "GB", "DE", "FR", "BR", "IN", "AU"}
    assert set(cus.card_funding) <= {"credit", "debit", "prepaid"}
    assert set(cus.card_brand) <= {"visa", "mastercard", "amex"}
    assert (cus.monthly_price_usd == cus.plan_tier.map(PRICES)).all()
    assert set(cus.payday_day_of_month.dropna().astype(int)) <= {1, 15, 28}
    known = cus.payday_day_of_month.notna().mean()
    assert 0.55 < known < 0.65


def test_one_experiment_invoice_per_customer_in_window(small: dict[str, pd.DataFrame]) -> None:
    inv = small["raw_invoices"]
    exp = inv[inv.is_experiment_invoice]
    assert exp.customer_id.is_unique and len(exp) == len(small["raw_customers"])
    assert exp.created_at.between(WINDOW_START, WINDOW_END).all()
    pre = inv[~inv.is_experiment_invoice]
    assert pre.created_at.between(pd.Timestamp("2025-03-01"), pd.Timestamp("2026-03-01")).all()
    amount = inv.customer_id.map(small["raw_customers"].set_index("customer_id").monthly_price_usd)
    assert (inv.amount_usd == amount).all()
    assert set(inv.status) <= {"paid", "uncollectible"}


def test_experiment_attempt_zero_failed_and_matches_assignment(
    small: dict[str, pd.DataFrame],
) -> None:
    a = _attempts(small)
    a0 = a[a.is_experiment_invoice & (a.attempt_number == 0)].set_index("customer_id")
    assert len(a0) == len(small["raw_customers"])
    assert (a0.outcome == "failed").all()
    assert a0.decline_code.isin(
        ["insufficient_funds", "expired_card", "do_not_honor", "generic_decline"]
    ).all()
    asg = small["raw_assignments"].set_index("customer_id")
    assert (asg.assigned_at == a0.attempted_at.reindex(asg.index)).all()
    inv = small["raw_invoices"].set_index("invoice_id")
    assert (a0.attempted_at == a0.invoice_id.map(inv.created_at)).all()


def test_attempt_sequence_invariants(small: dict[str, pd.DataFrame]) -> None:
    a = _attempts(small).sort_values(["invoice_id", "attempt_number"])
    g = a.groupby("invoice_id")
    # attempt numbers are 0..n-1 with at most 4 retries
    assert (g.attempt_number.min() == 0).all()
    assert (g.attempt_number.max() + 1 == g.size()).all()
    assert a.attempt_number.max() <= 4
    # at most one success, and it is the last attempt
    succ = a.outcome.eq("succeeded")
    assert (succ.groupby(a.invoice_id).sum() <= 1).all()
    last = g.tail(1).set_index("invoice_id")
    n_succ = succ.groupby(a.invoice_id).sum()
    assert ((n_succ == 1) == (last.outcome == "succeeded")).all()
    # paid <=> some attempt succeeded
    paid = g.status.first() == "paid"
    assert (paid == (n_succ == 1)).all()
    # decline_code null exactly when succeeded
    assert (a.decline_code.isna() == succ).all()
    # retries strictly increasing, within 7 days of attempt 0
    first = g.attempted_at.transform("min")
    assert (a.attempted_at - first <= 7 * DAY).all()
    assert (g.attempted_at.diff().dropna() > pd.Timedelta(0)).all()


def test_control_schedule_is_fixed(small: dict[str, pd.DataFrame]) -> None:
    a = _attempts(small)
    a = a[a.is_experiment_invoice]
    variant = a.customer_id.map(small["raw_assignments"].set_index("customer_id").variant)
    ctl = a[variant == "control"]
    t0 = ctl.groupby("invoice_id").attempted_at.transform("min")
    offset_days = {1: 1, 2: 3, 3: 5, 4: 7}
    expected = t0 + ctl.attempt_number.map(lambda k: offset_days.get(k, 0)) * DAY
    assert (ctl.attempted_at == expected).all()


def test_treatment_uses_payday_when_in_window(small: dict[str, pd.DataFrame]) -> None:
    a = _attempts(small)
    a = a[a.is_experiment_invoice]
    cus = small["raw_customers"].set_index("customer_id")
    variant = a.customer_id.map(small["raw_assignments"].set_index("customer_id").variant)
    trt = a[variant == "treatment"].copy()
    trt["payday"] = trt.customer_id.map(cus.payday_day_of_month)
    t0 = trt.groupby("invoice_id").attempted_at.transform("min")
    retries = trt[trt.attempt_number >= 1]
    assert (retries.attempted_at - t0.loc[retries.index] >= pd.Timedelta(hours=1)).all()

    # For unrecovered treatment invoices (full schedule visible) whose payday date falls strictly
    # inside the retry window, one retry must land on that payday's date.
    sizes = trt.groupby("invoice_id").size()
    full = trt[trt.invoice_id.map(sizes).eq(5) & trt.payday.notna()]
    checked = 0
    for _, s in full.groupby("invoice_id"):
        day0 = s.attempted_at.min().normalize()
        interior = [day0 + d * DAY for d in range(1, 7)]
        pay_dates = [d for d in interior if d.day == int(s.payday.iloc[0])]
        if not pay_dates:
            continue
        retry_dates = set(s[s.attempt_number >= 1].attempted_at.dt.normalize())
        assert pay_dates[0] in retry_dates
        checked += 1
    assert checked > 20


def test_treatment_recovers_earlier(
    small_exp: pd.DataFrame, small: dict[str, pd.DataFrame]
) -> None:
    a = _attempts(small)
    won = a[a.is_experiment_invoice & a.outcome.eq("succeeded")]
    variant = won.customer_id.map(small["raw_assignments"].set_index("customer_id").variant)
    mean_retry = won.attempt_number.groupby(variant).mean()
    assert mean_retry["treatment"] < mean_retry["control"]


def test_tickets_and_churn(small: dict[str, pd.DataFrame], small_exp: pd.DataFrame) -> None:
    tk, ev = small["raw_support_tickets"], small["raw_subscription_events"]
    assert set(tk.category) == {"billing_complaint", "other"}
    assert set(ev.event_type) == {"churned_involuntary", "churned_voluntary"}
    assert ev.customer_id.is_unique
    billing = tk[tk.category == "billing_complaint"].set_index("customer_id")
    delta = billing.created_at - small_exp.failed_at.reindex(billing.index)
    assert ((delta >= pd.Timedelta(0)) & (delta < 14 * DAY)).all()
    ev = ev.set_index("customer_id")
    delta = ev.event_at - small_exp.failed_at.reindex(ev.index)
    assert ((delta >= pd.Timedelta(0)) & (delta < 30 * DAY)).all()
    invol = ev[ev.event_type == "churned_involuntary"].index
    assert not small_exp.is_recovered.reindex(invol).any()
    assert (delta[ev.event_type == "churned_involuntary"] > 7 * DAY).all()


def test_no_expired_card_for_recent_signups(small: dict[str, pd.DataFrame]) -> None:
    inv = small["raw_invoices"]
    exp = inv[inv.is_experiment_invoice].set_index("customer_id")
    a = small["raw_payment_attempts"]
    a0 = a[a.invoice_id.isin(exp.invoice_id) & (a.attempt_number == 0)]
    code = a0.set_index("invoice_id").decline_code
    signup = small["raw_customers"].set_index("customer_id").signup_at
    tenure = exp.created_at - signup.reindex(exp.index)
    recent = exp.invoice_id[tenure < pd.Timedelta(days=183)]
    assert not (code.reindex(recent) == "expired_card").any()


def test_generate_returns_row_counts(
    small_run: tuple[Path, dict[str, int]], small: dict[str, pd.DataFrame]
) -> None:
    _, counts = small_run
    assert counts == {t: len(df) for t, df in small.items()}
