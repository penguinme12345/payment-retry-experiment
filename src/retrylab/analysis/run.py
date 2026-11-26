"""Orchestrates the analysis: marts → statistics → C6 ``results.json`` (+ figures)."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from retrylab.analysis.cuped import cuped
from retrylab.analysis.decide import decide
from retrylab.analysis.figures import make_figures
from retrylab.analysis.guardrails import evaluate_guardrails
from retrylab.analysis.impact import revenue_impact
from retrylab.analysis.io import (
    EXPERIMENT_ID,
    read_invoices,
    read_power_analysis,
    resolve,
)
from retrylab.analysis.means import welch_ttest
from retrylab.analysis.proportions import compare_proportions
from retrylab.analysis.schema import Results
from retrylab.analysis.segments import segment_lifts
from retrylab.analysis.srm import SRM_THRESHOLD, srm_check

CUPED_COVARIATE = "pre_failed_attempt_rate"
CI_LEVEL = 0.95
DECIMALS = 6

#: Secondary metrics: (C6 metric name, mart column, restrict to recovered invoices).
SECONDARY_METRICS: tuple[tuple[str, str, bool], ...] = (
    ("recovered_revenue_per_invoice_usd", "recovered_amount_usd", False),
    ("avg_retries_per_invoice", "retries_attempted", False),
    ("hours_to_recovery", "hours_to_recovery", True),
)


def _round(obj: Any) -> Any:
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return 0.0
        r = round(obj, DECIMALS)
        return 0.0 if r == 0 else r
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v) for v in obj]
    return obj


def _iso_utc(ts: datetime | None) -> str:
    ts = ts or datetime.now(UTC)
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    return ts.replace(microsecond=0).isoformat() + "Z"


def build_results(
    df: pd.DataFrame,
    power: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Compute every C6 field from an ``fct_experiment_invoices`` frame."""
    alpha = float(power.get("alpha", 0.05))
    is_t = (df["variant"] == "treatment").to_numpy()
    n_c, n_t = int((~is_t).sum()), int(is_t.sum())
    srm = srm_check(n_c, n_t, SRM_THRESHOLD)

    rec = df["is_recovered"].to_numpy(dtype=bool)
    p = compare_proportions(int((rec & ~is_t).sum()), n_c, int((rec & is_t).sum()), n_t, alpha)
    primary = {
        "metric": "recovery_rate",
        "control": p.control,
        "treatment": p.treatment,
        "abs_lift": p.abs_lift,
        "rel_lift": p.rel_lift,
        "ci_low": p.ci_low,
        "ci_high": p.ci_high,
        "ci_level": 1 - alpha,
        "p_value": p.p_value,
        "significant": bool(p.p_value < alpha),
    }

    cu = cuped(rec.astype(float), df[CUPED_COVARIATE].to_numpy(dtype=float), is_t, alpha)
    cuped_out = {
        "covariate": CUPED_COVARIATE,
        "abs_lift": cu.abs_lift,
        "ci_low": cu.ci_low,
        "ci_high": cu.ci_high,
        "variance_reduction_pct": cu.variance_reduction_pct,
    }

    secondary = []
    for metric, col, recovered_only in SECONDARY_METRICS:
        sub = df[df["is_recovered"]] if recovered_only else df
        vals = sub[col].astype(float)
        mask = (sub["variant"] == "treatment").to_numpy()
        m = welch_ttest(vals[~mask].dropna(), vals[mask].dropna(), alpha)
        secondary.append(
            {
                "metric": metric,
                "control": m.control,
                "treatment": m.treatment,
                "abs_lift": m.abs_lift,
                "ci_low": m.ci_low,
                "ci_high": m.ci_high,
                "p_value": m.p_value,
            }
        )

    guardrails = evaluate_guardrails(df, power["guardrails"], alpha)
    segments = segment_lifts(df, "is_recovered", alpha, fdr=0.05)
    dec = decide(srm.passed, primary["significant"], p.abs_lift, guardrails, segments)
    impact = revenue_impact(df, dec.decision, p.abs_lift, dec.positive_segments)

    results = {
        "experiment_id": EXPERIMENT_ID,
        "generated_at": _iso_utc(generated_at),
        "n_control": n_c,
        "n_treatment": n_t,
        "srm": {
            "chi2": srm.chi2,
            "p_value": srm.p_value,
            "passed": srm.passed,
            "threshold": srm.threshold,
        },
        "primary": primary,
        "cuped": cuped_out,
        "secondary": secondary,
        "guardrails": guardrails,
        "segments": segments,
        "revenue_impact": impact,
        "recommendation": {"decision": dec.decision, "rationale": dec.rationale},
    }
    results = _round(results)
    Results.model_validate(results)
    return results


def run_analysis(
    db_path: str | Path,
    out_dir: str | Path,
    power_path: str | Path | None = "reports/power_analysis.json",
    generated_at: datetime | None = None,
    figures: bool = True,
) -> dict[str, Any]:
    """Read the warehouse, write ``<out>/results.json`` and ``<out>/figures/*.png``."""
    out = resolve(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = read_invoices(db_path)
    results = build_results(df, read_power_analysis(power_path), generated_at)
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    if figures:
        make_figures(results, df, out / "figures")
    return results
