"""Two-proportion comparisons: pooled z-test and the Newcombe hybrid-score CI on the difference.

All differences are ``treatment − control``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import stats


@dataclass(frozen=True)
class ProportionResult:
    n_control: int
    n_treatment: int
    control: float
    treatment: float
    abs_lift: float
    rel_lift: float
    ci_low: float
    ci_high: float
    z: float
    p_value: float


def wilson_interval(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a single proportion."""
    if n <= 0:
        raise ValueError("n must be positive")
    z = stats.norm.ppf(1 - alpha / 2)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return centre - half, centre + half


def newcombe_diff_ci(
    x_control: int, n_control: int, x_treatment: int, n_treatment: int, alpha: float = 0.05
) -> tuple[float, float]:
    """Newcombe (1998, method 10) hybrid-score CI for ``p_treatment − p_control``."""
    p_c, p_t = x_control / n_control, x_treatment / n_treatment
    l_c, u_c = wilson_interval(x_control, n_control, alpha)
    l_t, u_t = wilson_interval(x_treatment, n_treatment, alpha)
    d = p_t - p_c
    low = d - math.sqrt((p_t - l_t) ** 2 + (u_c - p_c) ** 2)
    high = d + math.sqrt((u_t - p_t) ** 2 + (p_c - l_c) ** 2)
    return low, high


def two_proportion_ztest(
    x_control: int, n_control: int, x_treatment: int, n_treatment: int
) -> tuple[float, float]:
    """Pooled two-sided two-proportion z-test. Returns ``(z, p_value)``."""
    p_c, p_t = x_control / n_control, x_treatment / n_treatment
    pooled = (x_control + x_treatment) / (n_control + n_treatment)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_control + 1 / n_treatment))
    if se == 0:
        return 0.0, 1.0
    z = (p_t - p_c) / se
    return z, float(2 * stats.norm.sf(abs(z)))


def compare_proportions(
    x_control: int, n_control: int, x_treatment: int, n_treatment: int, alpha: float = 0.05
) -> ProportionResult:
    """Rates, absolute and relative lift, Newcombe CI and pooled z-test p-value."""
    if n_control <= 0 or n_treatment <= 0:
        raise ValueError("both arms need at least one unit")
    p_c, p_t = x_control / n_control, x_treatment / n_treatment
    low, high = newcombe_diff_ci(x_control, n_control, x_treatment, n_treatment, alpha)
    z, p = two_proportion_ztest(x_control, n_control, x_treatment, n_treatment)
    rel = (p_t - p_c) / p_c if p_c > 0 else float("nan")
    return ProportionResult(
        n_control=int(n_control),
        n_treatment=int(n_treatment),
        control=p_c,
        treatment=p_t,
        abs_lift=p_t - p_c,
        rel_lift=rel,
        ci_low=low,
        ci_high=high,
        z=z,
        p_value=p,
    )
