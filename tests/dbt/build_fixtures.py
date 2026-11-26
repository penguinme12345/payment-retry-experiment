"""Build the hand-made dbt fixtures (raw Parquet) and their expected mart values (CSV).

Each customer below is one edge case. The raw rows are generated from the customer's spec, and
the expected `fct_experiment_invoices` row is written by hand next to it, so the expectations do
not reuse the dbt logic. The aggregate expectations are rolled up from the hand-written fact rows.

Run from the repo root to regenerate (output is deterministic):

    python tests/dbt/build_fixtures.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "fixtures" / "raw"
EXPECTED_DIR = HERE / "expected"

TS = pa.timestamp("us")
SCHEMAS: dict[str, pa.Schema] = {
    "raw_customers": pa.schema(
        [
            ("customer_id", pa.string()),
            ("signup_at", TS),
            ("country", pa.string()),
            ("plan_tier", pa.string()),
            ("monthly_price_usd", pa.float64()),
            ("card_brand", pa.string()),
            ("card_funding", pa.string()),
            ("payday_day_of_month", pa.int32()),
        ]
    ),
    "raw_assignments": pa.schema(
        [
            ("customer_id", pa.string()),
            ("experiment_id", pa.string()),
            ("variant", pa.string()),
            ("assigned_at", TS),
        ]
    ),
    "raw_invoices": pa.schema(
        [
            ("invoice_id", pa.string()),
            ("customer_id", pa.string()),
            ("amount_usd", pa.float64()),
            ("created_at", TS),
            ("is_experiment_invoice", pa.bool_()),
            ("status", pa.string()),
        ]
    ),
    "raw_payment_attempts": pa.schema(
        [
            ("attempt_id", pa.string()),
            ("invoice_id", pa.string()),
            ("attempt_number", pa.int32()),
            ("attempted_at", TS),
            ("outcome", pa.string()),
            ("decline_code", pa.string()),
        ]
    ),
    "raw_support_tickets": pa.schema(
        [
            ("ticket_id", pa.string()),
            ("customer_id", pa.string()),
            ("created_at", TS),
            ("category", pa.string()),
        ]
    ),
    "raw_subscription_events": pa.schema(
        [("customer_id", pa.string()), ("event_type", pa.string()), ("event_at", TS)]
    ),
}

PRICES = {"basic": 9.0, "pro": 29.0, "business": 99.0}
D = timedelta(days=1)
H = timedelta(hours=1)

# A pre-period invoice: (created_at, attempt outcomes in order). Paid iff the last is "s".
PreInvoice = tuple[datetime, str]


def monthly_history() -> list[PreInvoice]:
    """Twelve clean monthly invoices, 2025-03-05 .. 2026-02-05, each paid on the first try."""
    return [(datetime(2025 + (2 + m) // 12, (2 + m) % 12 + 1, 5, 9), "s") for m in range(12)]


@dataclass
class Case:
    """One customer and the expected fact row for their experiment invoice."""

    note: str
    variant: str
    country: str
    plan_tier: str
    card_funding: str
    decline: str
    # Retries as (offset from failed_at, "s" | "f").
    retries: list[tuple[timedelta, str]]
    exp_recovered: bool
    exp_hours: float | None
    exp_ticket: bool
    exp_churn: bool
    exp_pre_paid: int
    exp_pre_rate: float
    tickets: list[tuple[timedelta, str]] = field(default_factory=list)  # offset, category
    events: list[tuple[timedelta, str]] = field(default_factory=list)  # offset, event_type
    history: list[PreInvoice] = field(default_factory=monthly_history)
    payday: int | None = 15
    failed_at: datetime = datetime(2026, 3, 10, 14, 0)


CASES: list[Case] = [
    Case(
        "recovered on retry 1 at +1d; has a post-period paid invoice (ignored)",
        "control",
        "US",
        "basic",
        "credit",
        "insufficient_funds",
        [(1 * D, "s")],
        True,
        24.0,
        False,
        False,
        12,
        0.0,
        history=[*monthly_history(), (datetime(2026, 4, 10, 9), "s")],
    ),
    Case(
        "recovered on retry 4 at exactly +7d (window end is inclusive)",
        "treatment",
        "US",
        "pro",
        "debit",
        "insufficient_funds",
        [(1 * D, "f"), (2 * D, "f"), (4 * D, "f"), (7 * D, "s")],
        True,
        168.0,
        False,
        False,
        12,
        0.0,
    ),
    Case(
        "all 4 retries fail",
        "control",
        "CA",
        "business",
        "credit",
        "do_not_honor",
        [(1 * D, "f"), (3 * D, "f"), (5 * D, "f"), (7 * D, "f")],
        False,
        None,
        False,
        False,
        12,
        0.0,
    ),
    Case(
        "prepaid + insufficient_funds, paid on day 8 = not recovered",
        "treatment",
        "GB",
        "basic",
        "prepaid",
        "insufficient_funds",
        [(1 * D, "f"), (3 * D, "f"), (8 * D, "s")],
        False,
        None,
        False,
        False,
        12,
        0.0,
    ),
    Case(
        "no pre-period history -> covariates are 0",
        "control",
        "DE",
        "pro",
        "credit",
        "expired_card",
        [(1 * D, "f"), (3 * D, "f"), (5 * D, "f"), (7 * D, "f")],
        False,
        None,
        False,
        False,
        0,
        0.0,
        history=[],
    ),
    Case(
        "billing ticket on day 15 is excluded; recovered at +2.5d",
        "treatment",
        "FR",
        "business",
        "debit",
        "generic_decline",
        [(1 * D, "f"), (2 * D + 12 * H, "s")],
        True,
        60.0,
        False,
        False,
        12,
        0.0,
        tickets=[(15 * D, "billing_complaint")],
    ),
    Case(
        "billing ticket day 3 and involuntary churn day 10",
        "control",
        "BR",
        "basic",
        "prepaid",
        "insufficient_funds",
        [(1 * D, "f"), (3 * D, "f"), (5 * D, "f"), (7 * D, "f")],
        False,
        None,
        True,
        True,
        12,
        0.0,
        tickets=[(3 * D, "billing_complaint")],
        events=[(10 * D, "churned_involuntary")],
    ),
    Case(
        "billing ticket exactly at +14d counts; an 'other' ticket does not; recovered at +6h",
        "treatment",
        "IN",
        "pro",
        "credit",
        "do_not_honor",
        [(6 * H, "s")],
        True,
        6.0,
        True,
        False,
        12,
        0.0,
        tickets=[(2 * D, "other"), (14 * D, "billing_complaint")],
    ),
    Case(
        "involuntary churn on day 31 is excluded",
        "control",
        "AU",
        "business",
        "debit",
        "generic_decline",
        [(1 * D, "f"), (3 * D, "f"), (5 * D, "f"), (7 * D, "f")],
        False,
        None,
        False,
        False,
        12,
        0.0,
        events=[(31 * D, "churned_involuntary")],
    ),
    Case(
        "voluntary churn does not count as involuntary; recovered on retry 3",
        "treatment",
        "US",
        "basic",
        "credit",
        "expired_card",
        [(1 * D, "f"), (3 * D, "f"), (5 * D, "s")],
        True,
        120.0,
        False,
        False,
        12,
        0.0,
        events=[(5 * D + 2 * H, "churned_voluntary")],
    ),
    Case(
        "billing ticket before the failure is excluded",
        "control",
        "CA",
        "pro",
        "prepaid",
        "insufficient_funds",
        [(1 * D, "f"), (3 * D, "s")],
        True,
        72.0,
        False,
        False,
        12,
        0.0,
        tickets=[(-2 * D, "billing_complaint")],
    ),
    Case(
        "no retries at all",
        "treatment",
        "GB",
        "business",
        "credit",
        "do_not_honor",
        [],
        False,
        None,
        False,
        False,
        12,
        0.0,
    ),
    Case(
        "mixed pre-period history; invoice before the pre-period is ignored",
        "control",
        "DE",
        "basic",
        "debit",
        "generic_decline",
        [(1 * D, "f"), (3 * D, "f"), (5 * D, "f"), (7 * D, "f")],
        False,
        None,
        False,
        False,
        11,
        7 / 18,
        # 10 clean invoices (10 attempts), one paid after 2 failures (3 attempts), one
        # uncollectible after 5 failures (5 attempts): 7 failed / 18 attempts, 11 paid.
        # Plus one pre-pre-period invoice with a failure that must be ignored.
        history=[
            (datetime(2025, 2, 5, 9), "fs"),
            *monthly_history()[:10],
            (datetime(2026, 1, 5, 9), "ffs"),
            (datetime(2026, 2, 5, 9), "fffff"),
        ],
    ),
    Case(
        "pre-period boundary invoices (first and last instant) are included",
        "treatment",
        "FR",
        "pro",
        "prepaid",
        "insufficient_funds",
        [(1 * D, "s")],
        True,
        24.0,
        False,
        False,
        2,
        1 / 3,
        history=[(datetime(2025, 3, 1, 0, 0), "s"), (datetime(2026, 2, 28, 23, 59), "fs")],
    ),
    Case(
        "involuntary churn exactly at +30d counts",
        "control",
        "BR",
        "business",
        "credit",
        "expired_card",
        [(1 * D, "f"), (3 * D, "f"), (5 * D, "f"), (7 * D, "f")],
        False,
        None,
        False,
        True,
        12,
        0.0,
        events=[(30 * D, "churned_involuntary")],
    ),
    Case(
        "ticket day 1 and churn day 20, not recovered",
        "treatment",
        "IN",
        "basic",
        "debit",
        "generic_decline",
        [(1 * D, "f"), (3 * D, "f"), (6 * D, "f")],
        False,
        None,
        True,
        True,
        12,
        0.0,
        tickets=[(1 * D, "billing_complaint")],
        events=[(20 * D, "churned_involuntary")],
    ),
    Case(
        "two billing tickets still flag once; recovered on retry 3",
        "control",
        "AU",
        "pro",
        "credit",
        "do_not_honor",
        [(1 * D, "f"), (3 * D, "f"), (5 * D, "s")],
        True,
        120.0,
        True,
        False,
        12,
        0.0,
        tickets=[(2 * D, "billing_complaint"), (4 * D, "billing_complaint")],
    ),
    Case(
        "unknown payday; recovered on retry 2 after 1.5 hours past +2d",
        "treatment",
        "US",
        "business",
        "prepaid",
        "expired_card",
        [(1 * D, "f"), (2 * D + 90 * timedelta(minutes=1), "s")],
        True,
        49.5,
        False,
        False,
        12,
        0.0,
        payday=None,
    ),
    Case(
        "paid 1 second after the 7-day window = not recovered",
        "control",
        "US",
        "basic",
        "debit",
        "insufficient_funds",
        [(1 * D, "f"), (3 * D, "f"), (5 * D, "f"), (7 * D + timedelta(seconds=1), "s")],
        False,
        None,
        False,
        False,
        12,
        0.0,
        failed_at=datetime(2026, 3, 31, 23, 59, 59),
    ),
    Case(
        "first day of the window, 4 failed retries",
        "treatment",
        "CA",
        "pro",
        "credit",
        "generic_decline",
        [(1 * D, "f"), (3 * D, "f"), (5 * D, "f"), (7 * D, "f")],
        False,
        None,
        False,
        False,
        12,
        0.0,
        failed_at=datetime(2026, 3, 1, 0, 0),
    ),
]

FCT_COLUMNS = [
    "invoice_id", "customer_id", "variant", "country", "plan_tier", "card_funding",
    "initial_decline_code", "amount_usd", "failed_at", "is_recovered", "recovered_at",
    "hours_to_recovery", "retries_attempted", "recovered_amount_usd", "had_billing_ticket_14d",
    "churned_involuntary_30d", "pre_paid_invoice_count", "pre_failed_attempt_rate",
]  # fmt: skip


def build() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Return the raw tables and the expected fact table."""
    rows: dict[str, list[dict]] = {name: [] for name in SCHEMAS}
    fct: list[dict] = []
    n_inv = n_att = n_tkt = 0

    def add_invoice(cid: str, amount: float, created: datetime, outcomes: str, exp: bool,
                    decline: str, offsets: list[timedelta] | None = None) -> str:  # fmt: skip
        nonlocal n_inv, n_att
        n_inv += 1
        inv = f"in_{n_inv:07d}"
        status = "paid" if outcomes.endswith("s") else "uncollectible"
        rows["raw_invoices"].append(
            dict(
                invoice_id=inv,
                customer_id=cid,
                amount_usd=amount,
                created_at=created,
                is_experiment_invoice=exp,
                status=status,
            )  # fmt: skip
        )
        for k, outcome in enumerate(outcomes):
            n_att += 1
            at = created + (offsets[k] if offsets else k * D)
            rows["raw_payment_attempts"].append(
                dict(
                    attempt_id=f"py_{n_att:08d}",
                    invoice_id=inv,
                    attempt_number=k,
                    attempted_at=at,
                    outcome="succeeded" if outcome == "s" else "failed",
                    decline_code=None if outcome == "s" else decline,
                )  # fmt: skip
            )
        return inv

    for i, c in enumerate(CASES, start=1):
        cid = f"cus_{i:06d}"
        price = PRICES[c.plan_tier]
        rows["raw_customers"].append(
            dict(
                customer_id=cid,
                signup_at=datetime(2024, 6, 1) + i * D,
                country=c.country,
                plan_tier=c.plan_tier,
                monthly_price_usd=price,
                card_brand=["visa", "mastercard", "amex"][i % 3],
                card_funding=c.card_funding,
                payday_day_of_month=c.payday,
            )  # fmt: skip
        )
        rows["raw_assignments"].append(
            dict(
                customer_id=cid,
                experiment_id="retry_timing_v1",
                variant=c.variant,
                assigned_at=c.failed_at,
            )  # fmt: skip
        )
        for created, outcomes in c.history:
            add_invoice(cid, price, created, outcomes, False, "insufficient_funds")
        outcomes = "f" + "".join(o for _, o in c.retries)
        offsets = [timedelta(0)] + [off for off, _ in c.retries]
        inv = add_invoice(cid, price, c.failed_at, outcomes, True, c.decline, offsets)
        for off, category in c.tickets:
            n_tkt += 1
            rows["raw_support_tickets"].append(
                dict(
                    ticket_id=f"tkt_{n_tkt:07d}",
                    customer_id=cid,
                    created_at=c.failed_at + off,
                    category=category,
                )  # fmt: skip
            )
        for off, event_type in c.events:
            rows["raw_subscription_events"].append(
                dict(customer_id=cid, event_type=event_type, event_at=c.failed_at + off)
            )
        recovered_at = c.failed_at + timedelta(hours=c.exp_hours) if c.exp_recovered else None
        fct.append(
            dict(
                invoice_id=inv,
                customer_id=cid,
                variant=c.variant,
                country=c.country,
                plan_tier=c.plan_tier,
                card_funding=c.card_funding,
                initial_decline_code=c.decline,
                amount_usd=price,
                failed_at=c.failed_at,
                is_recovered=c.exp_recovered,
                recovered_at=recovered_at,
                hours_to_recovery=c.exp_hours,
                retries_attempted=len(c.retries),
                recovered_amount_usd=price if c.exp_recovered else 0.0,
                had_billing_ticket_14d=c.exp_ticket,
                churned_involuntary_30d=c.exp_churn,
                pre_paid_invoice_count=c.exp_pre_paid,
                pre_failed_attempt_rate=c.exp_pre_rate,
            )  # fmt: skip
        )

    raw = {name: pd.DataFrame(r, columns=SCHEMAS[name].names) for name, r in rows.items()}
    return raw, pd.DataFrame(fct, columns=FCT_COLUMNS)


def expected_summary(fct: pd.DataFrame) -> pd.DataFrame:
    """Roll the expected fact rows up to one row per variant."""
    g = fct.groupby("variant", sort=True)
    out = pd.DataFrame(
        {
            "n_invoices": g.size(),
            "n_recovered": g["is_recovered"].sum(),
            "recovered_revenue_usd": g["recovered_amount_usd"].sum().round(2),
            "retries": g["retries_attempted"].sum(),
            "tickets": g["had_billing_ticket_14d"].sum(),
            "churn": g["churned_involuntary_30d"].sum(),
        }
    )
    out["recovery_rate"] = out.n_recovered / out.n_invoices
    out["recovered_revenue_per_invoice_usd"] = out.recovered_revenue_usd / out.n_invoices
    out["avg_retries_per_invoice"] = out.retries / out.n_invoices
    out["billing_ticket_rate"] = out.tickets / out.n_invoices
    out["involuntary_churn_rate"] = out.churn / out.n_invoices
    cols = ["n_invoices", "n_recovered", "recovery_rate", "recovered_revenue_usd",
            "recovered_revenue_per_invoice_usd", "avg_retries_per_invoice",
            "billing_ticket_rate", "involuntary_churn_rate"]  # fmt: skip
    return out[cols].reset_index()


def expected_segments(fct: pd.DataFrame) -> pd.DataFrame:
    """Roll the expected fact rows up to (variant, segment_dimension, segment_value)."""
    parts = []
    for dim in ["country", "plan_tier", "card_funding", "initial_decline_code"]:
        g = fct.groupby(["variant", dim], sort=True)
        part = pd.DataFrame(
            {
                "n_invoices": g.size(),
                "n_recovered": g["is_recovered"].sum(),
                "revenue": g["recovered_amount_usd"].sum(),
            }
        ).reset_index()
        part = part.rename(columns={dim: "segment_value"})
        part.insert(1, "segment_dimension", dim)
        parts.append(part)
    out = pd.concat(parts, ignore_index=True)
    out["recovery_rate"] = out.n_recovered / out.n_invoices
    out["recovered_revenue_per_invoice_usd"] = out.revenue / out.n_invoices
    cols = ["variant", "segment_dimension", "segment_value", "n_invoices", "n_recovered",
            "recovery_rate", "recovered_revenue_per_invoice_usd"]  # fmt: skip
    return out[cols].sort_values(cols[:3]).reset_index(drop=True)


def main() -> None:
    raw, fct = build()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in raw.items():
        table = pa.Table.from_pandas(df, schema=SCHEMAS[name], preserve_index=False)
        pq.write_table(table, RAW_DIR / f"{name}.parquet")
    fct.to_csv(EXPECTED_DIR / "fct_experiment_invoices.csv", index=False)
    expected_summary(fct).to_csv(EXPECTED_DIR / "agg_experiment_summary.csv", index=False)
    expected_segments(fct).to_csv(EXPECTED_DIR / "agg_experiment_segments.csv", index=False)
    print(f"wrote {len(CASES)} customers to {RAW_DIR} and expectations to {EXPECTED_DIR}")


if __name__ == "__main__":
    main()
