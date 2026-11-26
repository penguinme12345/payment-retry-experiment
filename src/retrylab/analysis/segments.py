"""Per-segment lift on the primary metric with Benjamini–Hochberg FDR control."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from retrylab.analysis.io import SEGMENT_VALUES
from retrylab.analysis.proportions import compare_proportions


def benjamini_hochberg(p_values: list[float] | np.ndarray) -> np.ndarray:
    """BH step-up adjusted p-values (monotone, capped at 1)."""
    p = np.asarray(p_values, dtype=float)
    m = p.size
    if m == 0:
        return p
    order = np.argsort(p, kind="mergesort")
    ranked = p[order] * m / np.arange(1, m + 1)
    adj_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(adj_sorted, 1.0)
    return out


def segment_lifts(
    df: pd.DataFrame,
    metric_col: str = "is_recovered",
    alpha: float = 0.05,
    fdr: float = 0.05,
) -> list[dict[str, Any]]:
    """One row per (dimension, value) in C2 that has units in both arms.

    BH is applied across all rows together; ``significant_adj = p_value_adj < fdr``.
    """
    rows: list[dict[str, Any]] = []
    is_t = df["variant"].to_numpy() == "treatment"
    y = df[metric_col].to_numpy(dtype=bool)
    for dim, values in SEGMENT_VALUES.items():
        col = df[dim].to_numpy()
        for value in values:
            seg = col == value
            n_c, n_t = int((seg & ~is_t).sum()), int((seg & is_t).sum())
            if n_c == 0 or n_t == 0:
                continue
            x_c, x_t = int((y & seg & ~is_t).sum()), int((y & seg & is_t).sum())
            r = compare_proportions(x_c, n_c, x_t, n_t, alpha)
            rows.append(
                {
                    "dimension": dim,
                    "value": value,
                    "n_control": n_c,
                    "n_treatment": n_t,
                    "control_rate": r.control,
                    "treatment_rate": r.treatment,
                    "abs_lift": r.abs_lift,
                    "ci_low": r.ci_low,
                    "ci_high": r.ci_high,
                    "p_value": r.p_value,
                }
            )
    adj = benjamini_hochberg([r["p_value"] for r in rows])
    for row, p_adj in zip(rows, adj, strict=True):
        row["p_value_adj"] = float(p_adj)
        row["significant_adj"] = bool(p_adj < fdr)
    return rows
