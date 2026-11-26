"""Guardrail metrics: lift, CI, and a one-sided breach rule against the allowed increase."""

from __future__ import annotations

from typing import Any

import pandas as pd

from retrylab.analysis.proportions import compare_proportions

#: Guardrail metric name (C4 semantic layer) → boolean column in ``fct_experiment_invoices``.
GUARDRAIL_COLUMNS: dict[str, str] = {
    "billing_ticket_rate": "had_billing_ticket_14d",
    "involuntary_churn_rate": "churned_involuntary_30d",
}


def is_breached(ci_low: float, threshold_abs: float) -> bool:
    """Breached when we are confident the increase exceeds the allowance: ``ci_low > threshold``."""
    return bool(ci_low > threshold_abs)


def evaluate_guardrails(
    df: pd.DataFrame, guardrails: list[dict[str, Any]], alpha: float = 0.05
) -> list[dict[str, Any]]:
    """Evaluate every guardrail listed in C5 that maps to a mart column."""
    is_t = df["variant"].to_numpy() == "treatment"
    n_c, n_t = int((~is_t).sum()), int(is_t.sum())
    out: list[dict[str, Any]] = []
    for g in guardrails:
        metric = g["metric"]
        if metric not in GUARDRAIL_COLUMNS:
            raise ValueError(f"unknown guardrail metric {metric!r}")
        y = df[GUARDRAIL_COLUMNS[metric]].to_numpy(dtype=bool)
        r = compare_proportions(int((y & ~is_t).sum()), n_c, int((y & is_t).sum()), n_t, alpha)
        threshold = float(g["max_acceptable_increase_abs"])
        out.append(
            {
                "metric": metric,
                "control": r.control,
                "treatment": r.treatment,
                "abs_lift": r.abs_lift,
                "ci_low": r.ci_low,
                "ci_high": r.ci_high,
                "p_value": r.p_value,
                "threshold_abs": threshold,
                "breached": is_breached(r.ci_low, threshold),
            }
        )
    return out
