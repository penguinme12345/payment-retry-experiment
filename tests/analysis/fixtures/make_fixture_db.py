"""Build a small DuckDB with C4-shaped marts and *known* planted effects.

``python tests/analysis/fixtures/make_fixture_db.py --out /tmp/fixture.duckdb``

Default: 4,000 invoices, +5pp recovery lift for ``initial_decline_code = insufficient_funds``
and no effect anywhere else. Everything is seeded.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

COUNTRIES = ["US", "CA", "GB", "DE", "FR", "BR", "IN", "AU"]
TIERS = ["basic", "pro", "business"]
PRICES = {"basic": 9.0, "pro": 29.0, "business": 99.0}
FUNDING = ["credit", "debit", "prepaid"]
DECLINES = ["insufficient_funds", "expired_card", "do_not_honor", "generic_decline"]
BASE_RATES = {
    "insufficient_funds": 0.45,
    "expired_card": 0.15,
    "do_not_honor": 0.30,
    "generic_decline": 0.35,
}
WINDOW_START = datetime(2026, 3, 1)

DEFAULT_EFFECTS: dict[tuple[str, str], float] = {
    ("initial_decline_code", "insufficient_funds"): 0.05
}


def make_invoices(
    n: int = 4000,
    seed: int = 0,
    effects: Mapping[tuple[str, str], float] | None = None,
    treatment_share: float = 0.5,
    covariate_slope: float = 0.6,
    billing_rates: tuple[float, float] = (0.03, 0.03),
    churn_rates: tuple[float, float] = (0.40, 0.40),
) -> pd.DataFrame:
    """Return a ``fct_experiment_invoices`` frame with planted additive recovery effects.

    Recovery probability = base rate by decline code − ``covariate_slope`` ×
    (``pre_failed_attempt_rate`` − 0.1) + Σ planted effects (treatment only), clipped to [0, 1].
    """
    effects = DEFAULT_EFFECTS if effects is None else effects
    rng = np.random.default_rng(seed)
    variant = np.where(rng.random(n) < treatment_share, "treatment", "control")
    is_t = variant == "treatment"
    country = rng.choice(COUNTRIES, n)
    tier = rng.choice(TIERS, n, p=[0.5, 0.35, 0.15])
    funding = rng.choice(FUNDING, n, p=[0.55, 0.35, 0.10])
    decline = rng.choice(DECLINES, n, p=[0.4, 0.15, 0.2, 0.25])
    pfr = np.clip(rng.beta(1.2, 10, n), 0, 1)
    p = np.array([BASE_RATES[d] for d in decline]) - covariate_slope * (pfr - 0.1)
    cols = {
        "country": country,
        "plan_tier": tier,
        "card_funding": funding,
        "initial_decline_code": decline,
    }
    for (dim, value), lift in effects.items():
        p = p + lift * (is_t & (cols[dim] == value))
    recovered = rng.random(n) < np.clip(p, 0, 1)

    amount = np.array([PRICES[t] for t in tier])
    failed_at = [WINDOW_START + timedelta(seconds=int(s)) for s in rng.integers(0, 31 * 86400, n)]
    hours = np.where(recovered, rng.uniform(1, 7 * 24, n), np.nan)
    hours = np.where(recovered & is_t, hours * 0.8, hours)
    retries = np.where(recovered, rng.integers(1, 5, n), 4)
    bill = rng.random(n) < np.where(is_t, billing_rates[1], billing_rates[0])
    churn = (~recovered) & (rng.random(n) < np.where(is_t, churn_rates[1], churn_rates[0]))
    return pd.DataFrame(
        {
            "invoice_id": [f"in_{i:07d}" for i in range(1, n + 1)],
            "customer_id": [f"cus_{i:06d}" for i in range(1, n + 1)],
            "variant": variant,
            "country": country,
            "plan_tier": tier,
            "card_funding": funding,
            "initial_decline_code": decline,
            "amount_usd": amount,
            "failed_at": pd.to_datetime(failed_at),
            "is_recovered": recovered,
            "recovered_at": [
                f + timedelta(hours=float(h)) if r else pd.NaT
                for f, h, r in zip(failed_at, hours, recovered, strict=True)
            ],
            "hours_to_recovery": hours,
            "retries_attempted": retries.astype("int32"),
            "recovered_amount_usd": np.where(recovered, amount, 0.0),
            "had_billing_ticket_14d": bill,
            "churned_involuntary_30d": churn,
            "pre_paid_invoice_count": (12 - np.round(pfr * 12)).astype("int32"),
            "pre_failed_attempt_rate": pfr,
        }
    )


def write_fixture_db(df: pd.DataFrame, path: str | Path) -> Path:
    """Write ``fct_experiment_invoices`` and the two C4 aggregates into a fresh DuckDB file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with duckdb.connect(str(path)) as con:
        con.register("df", df)
        con.execute("create table main.fct_experiment_invoices as select * from df")
        con.execute(
            """
            create table main.agg_experiment_summary as
            select variant, count(*) as n_invoices,
                   sum(is_recovered::int) as n_recovered,
                   avg(is_recovered::double) as recovery_rate,
                   sum(recovered_amount_usd) as recovered_revenue_usd,
                   avg(recovered_amount_usd) as recovered_revenue_per_invoice_usd,
                   avg(retries_attempted) as avg_retries_per_invoice,
                   avg(had_billing_ticket_14d::double) as billing_ticket_rate,
                   avg(churned_involuntary_30d::double) as involuntary_churn_rate
            from fct_experiment_invoices group by variant
            """
        )
        unions = " union all ".join(
            f"select variant, '{d}' as segment_dimension, {d} as segment_value, "
            "count(*) as n_invoices, sum(is_recovered::int) as n_recovered, "
            "avg(is_recovered::double) as recovery_rate, "
            "avg(recovered_amount_usd) as recovered_revenue_per_invoice_usd "
            f"from fct_experiment_invoices group by variant, {d}"
            for d in ("country", "plan_tier", "card_funding", "initial_decline_code")
        )
        con.execute(f"create table main.agg_experiment_segments as {unions}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--n", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    write_fixture_db(make_invoices(args.n, args.seed), args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
