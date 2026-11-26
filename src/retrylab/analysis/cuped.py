"""CUPED variance reduction (Deng et al., 2013) with a single pre-period covariate."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from retrylab.analysis.means import welch_ttest


@dataclass(frozen=True)
class CupedResult:
    theta: float
    abs_lift: float
    ci_low: float
    ci_high: float
    p_value: float
    variance_reduction_pct: float


def cuped_adjust(y: ArrayLike, x: ArrayLike) -> tuple[np.ndarray, float]:
    """Return ``(Y_adj, θ)`` with θ = cov(Y, X)/var(X) on the pooled data."""
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    var_x = float(np.var(x, ddof=1))
    theta = 0.0 if var_x == 0 else float(np.cov(y, x, ddof=1)[0, 1] / var_x)
    return y - theta * (x - x.mean()), theta


def cuped(y: ArrayLike, x: ArrayLike, is_treatment: ArrayLike, alpha: float = 0.05) -> CupedResult:
    """CUPED-adjusted lift: Welch test on ``Y_adj`` between arms.

    ``variance_reduction_pct = 100·(1 − var(Y_adj)/var(Y))`` on the pooled data.
    """
    y = np.asarray(y, dtype=float)
    mask = np.asarray(is_treatment, dtype=bool)
    y_adj, theta = cuped_adjust(y, x)
    res = welch_ttest(y_adj[~mask], y_adj[mask], alpha)
    var_y = float(np.var(y, ddof=1))
    vr = 0.0 if var_y == 0 else 100.0 * (1.0 - float(np.var(y_adj, ddof=1)) / var_y)
    return CupedResult(theta, res.abs_lift, res.ci_low, res.ci_high, res.p_value, vr)
