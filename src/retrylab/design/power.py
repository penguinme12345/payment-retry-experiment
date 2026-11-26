"""Sample size and power for a two-proportion z-test (normal approximation).

Conventions used throughout:

* ``p_baseline`` is the control rate p1; the alternative is p2 = p1 + ``mde_abs``.
* The test statistic's variance is pooled under H0 (p̄ = (p1 + p2) / 2) and unpooled under H1,
  which is the textbook (Fleiss, no continuity correction) formula::

      n = (z_{1-a} * sqrt(2 p̄ q̄) + z_{1-b} * sqrt(p1 q1 + p2 q2))^2 / (p2 - p1)^2

  with z_{1-a} replaced by z_{1-a/2} for a two-sided test.
* ``achieved_power`` includes both rejection tails for a two-sided test; the far tail is
  negligible for any realistic effect, so it agrees with ``required_n_per_arm`` to rounding.
"""

from __future__ import annotations

import math

from scipy.optimize import brentq
from scipy.stats import norm

__all__ = [
    "achieved_power",
    "cohens_h",
    "mde_for_n",
    "required_n_per_arm",
    "required_n_per_arm_continuous",
    "statsmodels_n_per_arm",
]


def _validate(p_baseline: float, alpha: float, power: float | None = None) -> None:
    if not 0.0 < p_baseline < 1.0:
        raise ValueError(f"p_baseline must be in (0, 1), got {p_baseline}")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if power is not None and not 0.0 < power < 1.0:
        raise ValueError(f"power must be in (0, 1), got {power}")


def _z_alpha(alpha: float, two_sided: bool) -> float:
    return float(norm.ppf(1.0 - alpha / 2.0 if two_sided else 1.0 - alpha))


def _treatment_rate(p_baseline: float, mde_abs: float) -> float:
    p2 = p_baseline + mde_abs
    if mde_abs == 0.0:
        raise ValueError("mde_abs must be non-zero")
    if not 0.0 < p2 < 1.0:
        raise ValueError(f"p_baseline + mde_abs must be in (0, 1), got {p2}")
    return p2


def required_n_per_arm_continuous(
    p_baseline: float,
    mde_abs: float,
    alpha: float = 0.05,
    power: float = 0.8,
    two_sided: bool = True,
) -> float:
    """Un-rounded per-arm sample size from the closed-form formula in the module docstring."""
    _validate(p_baseline, alpha, power)
    p1 = p_baseline
    p2 = _treatment_rate(p1, mde_abs)
    p_bar = (p1 + p2) / 2.0
    se_null = math.sqrt(2.0 * p_bar * (1.0 - p_bar))
    se_alt = math.sqrt(p1 * (1.0 - p1) + p2 * (1.0 - p2))
    z_a = _z_alpha(alpha, two_sided)
    z_b = float(norm.ppf(power))
    return (z_a * se_null + z_b * se_alt) ** 2 / (p2 - p1) ** 2


def required_n_per_arm(
    p_baseline: float,
    mde_abs: float,
    alpha: float = 0.05,
    power: float = 0.8,
    two_sided: bool = True,
) -> int:
    """Per-arm sample size to detect an absolute lift of ``mde_abs`` (rounded up)."""
    n = required_n_per_arm_continuous(p_baseline, mde_abs, alpha, power, two_sided)
    # Guard against float noise turning an exact integer into the next one up.
    return int(math.ceil(n - 1e-9))


def achieved_power(
    p_baseline: float,
    mde_abs: float,
    n_per_arm: float,
    alpha: float = 0.05,
    two_sided: bool = True,
) -> float:
    """Power of the test to detect ``mde_abs`` with ``n_per_arm`` units in each arm."""
    _validate(p_baseline, alpha)
    if n_per_arm <= 0:
        raise ValueError(f"n_per_arm must be positive, got {n_per_arm}")
    p1 = p_baseline
    p2 = _treatment_rate(p1, mde_abs)
    p_bar = (p1 + p2) / 2.0
    se_null = math.sqrt(2.0 * p_bar * (1.0 - p_bar) / n_per_arm)
    se_alt = math.sqrt((p1 * (1.0 - p1) + p2 * (1.0 - p2)) / n_per_arm)
    z_a = _z_alpha(alpha, two_sided)
    delta = abs(p2 - p1)
    pw = float(norm.cdf((delta - z_a * se_null) / se_alt))
    if two_sided:
        pw += float(norm.cdf((-delta - z_a * se_null) / se_alt))
    return pw


def mde_for_n(
    p_baseline: float,
    n_per_arm: float,
    alpha: float = 0.05,
    power: float = 0.8,
    two_sided: bool = True,
) -> float:
    """Smallest positive absolute lift detectable with ``n_per_arm`` per arm (solved numerically).

    Inverts :func:`required_n_per_arm_continuous`, so
    ``mde_for_n(p, required_n_per_arm(p, d)) ≈ d`` (slightly below it, because n is rounded up).
    """
    _validate(p_baseline, alpha, power)
    if n_per_arm <= 0:
        raise ValueError(f"n_per_arm must be positive, got {n_per_arm}")

    def gap(d: float) -> float:
        return required_n_per_arm_continuous(p_baseline, d, alpha, power, two_sided) - n_per_arm

    lo = 1e-9
    hi = (1.0 - p_baseline) - 1e-9
    if gap(hi) > 0:
        raise ValueError(
            f"n_per_arm={n_per_arm} is too small to detect any lift from p={p_baseline}"
        )
    return float(brentq(gap, lo, hi, xtol=1e-12, rtol=1e-12, maxiter=500))


def cohens_h(p1: float, p2: float) -> float:
    """Cohen's effect size h for two proportions."""
    return 2.0 * math.asin(math.sqrt(p2)) - 2.0 * math.asin(math.sqrt(p1))


def statsmodels_n_per_arm(
    p_baseline: float,
    mde_abs: float,
    alpha: float = 0.05,
    power: float = 0.8,
    two_sided: bool = True,
) -> float:
    """Reference per-arm n from ``statsmodels`` ``NormalIndPower`` using Cohen's h."""
    from statsmodels.stats.power import NormalIndPower

    h = abs(cohens_h(p_baseline, p_baseline + mde_abs))
    return float(
        NormalIndPower().solve_power(
            effect_size=h,
            alpha=alpha,
            power=power,
            ratio=1.0,
            alternative="two-sided" if two_sided else "larger",
        )
    )
