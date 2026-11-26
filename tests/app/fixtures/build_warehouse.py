"""Build the small fixture warehouse that matches contract C4.

``build(path)`` writes ``fct_experiment_invoices`` (600 seeded synthetic rows) and derives
``agg_experiment_summary`` and ``agg_experiment_segments`` from it with SQL, so the three tables
are mutually consistent. Run directly to (re)build ``tests/app/fixtures/warehouse.duckdb``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

N_INVOICES = 600
SEED = 20260301
COUNTRIES = ["US", "CA", "GB", "DE", "FR", "BR", "IN", "AU"]
PLANS = {"basic": 9.0, "pro": 29.0, "business": 99.0}
FUNDING = ["credit", "debit", "prepaid"]
DECLINES = ["insufficient_funds", "expired_card", "do_not_honor", "generic_decline"]
BASE_RATE = {
    "insufficient_funds": 0.45,
    "expired_card": 0.15,
    "do_not_honor": 0.30,
    "generic_decline": 0.35,
}
TREAT_LIFT = {
    "insufficient_funds": 0.07,
    "expired_card": 0.0,
    "do_not_honor": 0.0,
    "generic_decline": 0.01,
}


def fact_table() -> pd.DataFrame:
    """Synthetic ``fct_experiment_invoices`` rows (deterministic)."""
    rng = np.random.default_rng(SEED)
    rows = []
    start = datetime(2026, 3, 1)
    for i in range(N_INVOICES):
        variant = "control" if i % 2 == 0 else "treatment"
        plan = list(PLANS)[rng.integers(0, 3)]
        decline = DECLINES[rng.integers(0, 4)]
        failed_at = start + timedelta(seconds=int(rng.integers(0, 31 * 86400)))
        rate = BASE_RATE[decline] + (TREAT_LIFT[decline] if variant == "treatment" else 0.0)
        recovered = bool(rng.random() < rate)
        if recovered:
            retries = int(rng.integers(1, 5))
            day = {"control": [1, 3, 5, 7], "treatment": [0.6, 2.2, 4.1, 6.5]}[variant][retries - 1]
            hours = round(day * 24 + float(rng.uniform(0, 6)), 4)
            hours = min(hours, 168.0)
            recovered_at = failed_at + timedelta(hours=hours)
        else:
            retries, hours, recovered_at = 4, None, None
        amount = PLANS[plan]
        rows.append(
            {
                "invoice_id": f"in_{i + 1:07d}",
                "customer_id": f"cus_{i + 1:06d}",
                "variant": variant,
                "country": COUNTRIES[rng.integers(0, len(COUNTRIES))],
                "plan_tier": plan,
                "card_funding": FUNDING[rng.integers(0, 3)],
                "initial_decline_code": decline,
                "amount_usd": amount,
                "failed_at": failed_at,
                "is_recovered": recovered,
                "recovered_at": recovered_at,
                "hours_to_recovery": hours,
                "retries_attempted": retries,
                "recovered_amount_usd": amount if recovered else 0.0,
                "had_billing_ticket_14d": bool(rng.random() < 0.03),
                "churned_involuntary_30d": (not recovered) and bool(rng.random() < 0.6),
                "pre_paid_invoice_count": int(rng.integers(8, 13)),
                "pre_failed_attempt_rate": round(float(rng.uniform(0, 0.2)), 4),
            }
        )
    df = pd.DataFrame(rows)
    df["retries_attempted"] = df["retries_attempted"].astype("int32")
    df["pre_paid_invoice_count"] = df["pre_paid_invoice_count"].astype("int32")
    return df


SUMMARY_SQL = """
CREATE TABLE agg_experiment_summary AS
SELECT variant,
       CAST(COUNT(*) AS INTEGER) AS n_invoices,
       CAST(SUM(is_recovered::INTEGER) AS INTEGER) AS n_recovered,
       AVG(is_recovered::DOUBLE) AS recovery_rate,
       SUM(recovered_amount_usd) AS recovered_revenue_usd,
       AVG(recovered_amount_usd) AS recovered_revenue_per_invoice_usd,
       AVG(retries_attempted) AS avg_retries_per_invoice,
       AVG(had_billing_ticket_14d::DOUBLE) AS billing_ticket_rate,
       AVG(churned_involuntary_30d::DOUBLE) AS involuntary_churn_rate
FROM fct_experiment_invoices GROUP BY variant ORDER BY variant
"""

SEGMENTS_SQL = """
CREATE TABLE agg_experiment_segments AS
WITH long AS (
    SELECT variant, 'country' AS segment_dimension, country AS segment_value, is_recovered,
           recovered_amount_usd FROM fct_experiment_invoices
    UNION ALL SELECT variant, 'plan_tier', plan_tier, is_recovered, recovered_amount_usd
        FROM fct_experiment_invoices
    UNION ALL SELECT variant, 'card_funding', card_funding, is_recovered, recovered_amount_usd
        FROM fct_experiment_invoices
    UNION ALL SELECT variant, 'initial_decline_code', initial_decline_code, is_recovered,
           recovered_amount_usd FROM fct_experiment_invoices
)
SELECT variant, segment_dimension, segment_value,
       CAST(COUNT(*) AS INTEGER) AS n_invoices,
       CAST(SUM(is_recovered::INTEGER) AS INTEGER) AS n_recovered,
       AVG(is_recovered::DOUBLE) AS recovery_rate,
       AVG(recovered_amount_usd) AS recovered_revenue_per_invoice_usd
FROM long GROUP BY ALL ORDER BY segment_dimension, segment_value, variant
"""


def build(path: Path) -> Path:
    """Write the fixture warehouse to ``path`` (replacing it). Returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    df = fact_table()
    con = duckdb.connect(str(path))
    try:
        con.register("fact_df", df)
        con.execute("CREATE TABLE fct_experiment_invoices AS SELECT * FROM fact_df")
        con.execute(SUMMARY_SQL)
        con.execute(SEGMENTS_SQL)
    finally:
        con.close()
    return path


if __name__ == "__main__":
    default = Path(__file__).with_name("warehouse.duckdb")
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    print(build(target))
