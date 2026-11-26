"""Read the C4 marts (read-only) and the C5 power analysis (with C5 defaults as fallback)."""

from __future__ import annotations

import json
import os
import warnings
from copy import deepcopy
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

EXPERIMENT_ID = "retry_timing_v1"
VARIANTS = ("control", "treatment")

#: C2 segment dimensions and their values, in contract order.
SEGMENT_VALUES: dict[str, tuple[str, ...]] = {
    "country": ("US", "CA", "GB", "DE", "FR", "BR", "IN", "AU"),
    "plan_tier": ("basic", "pro", "business"),
    "card_funding": ("credit", "debit", "prepaid"),
    "initial_decline_code": (
        "insufficient_funds",
        "expired_card",
        "do_not_honor",
        "generic_decline",
    ),
}

FCT_COLUMNS = (
    "invoice_id",
    "customer_id",
    "variant",
    "country",
    "plan_tier",
    "card_funding",
    "initial_decline_code",
    "amount_usd",
    "failed_at",
    "is_recovered",
    "recovered_at",
    "hours_to_recovery",
    "retries_attempted",
    "recovered_amount_usd",
    "had_billing_ticket_14d",
    "churned_involuntary_30d",
    "pre_paid_invoice_count",
    "pre_failed_attempt_rate",
)

#: C5 defaults, used when ``reports/power_analysis.json`` is missing.
DEFAULT_POWER_ANALYSIS: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "primary_metric": "recovery_rate",
    "baseline_rate": 0.345,
    "mde_abs": 0.02,
    "alpha": 0.05,
    "power": 0.8,
    "two_sided": True,
    "required_n_per_arm": 8983,
    "planned_n_per_arm": 25000,
    "achieved_power_at_mde": 0.997,
    "mde_curve": [],
    "guardrails": [
        {"metric": "billing_ticket_rate", "max_acceptable_increase_abs": 0.005},
        {"metric": "involuntary_churn_rate", "max_acceptable_increase_abs": 0.0},
    ],
}


def project_root() -> Path:
    """``$PROJECT_ROOT`` if set, else the current working directory (C1)."""
    return Path(os.environ.get("PROJECT_ROOT") or Path.cwd())


def resolve(path: str | Path) -> Path:
    """Resolve a relative path against :func:`project_root`."""
    p = Path(path)
    return p if p.is_absolute() else project_root() / p


def read_invoices(db_path: str | Path) -> pd.DataFrame:
    """Load ``main.fct_experiment_invoices`` from DuckDB, opened read-only."""
    path = resolve(db_path)
    if not path.exists():
        raise FileNotFoundError(f"warehouse not found: {path}")
    cols = ", ".join(FCT_COLUMNS)
    with duckdb.connect(str(path), read_only=True) as con:
        df = con.execute(f"select {cols} from main.fct_experiment_invoices").df()
    unknown = set(df["variant"].unique()) - set(VARIANTS)
    if unknown:
        raise ValueError(f"unexpected variants in fct_experiment_invoices: {sorted(unknown)}")
    for col in ("is_recovered", "had_billing_ticket_14d", "churned_involuntary_30d"):
        df[col] = df[col].astype(bool)
    df["pre_failed_attempt_rate"] = df["pre_failed_attempt_rate"].astype(float).fillna(0.0)
    return df.sort_values("invoice_id", kind="mergesort").reset_index(drop=True)


def read_power_analysis(path: str | Path | None) -> dict[str, Any]:
    """Read C5; fall back to :data:`DEFAULT_POWER_ANALYSIS` (with a warning) if it's missing."""
    defaults = deepcopy(DEFAULT_POWER_ANALYSIS)
    if path is None:
        return defaults
    p = resolve(path)
    if not p.exists():
        warnings.warn(f"{p} not found; using C5 default thresholds", stacklevel=2)
        return defaults
    data = json.loads(p.read_text())
    return {**defaults, **data}
