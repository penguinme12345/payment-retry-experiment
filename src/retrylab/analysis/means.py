"""Welch's t-test and CI for a difference in means (``treatment − control``)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike
from scipy import stats


@dataclass(frozen=True)
class MeanResult:
    control: float
    treatment: float
    abs_lift: float
    ci_low: float
    ci_high: float
    t: float
    df: float
    p_value: float


def welch_ttest(control: ArrayLike, treatment: ArrayLike, alpha: float = 0.05) -> MeanResult:
    """Welch's unequal-variance t-test with a Welch–Satterthwaite CI on the mean difference."""
    c = np.asarray(control, dtype=float)
    t = np.asarray(treatment, dtype=float)
    if c.size < 2 or t.size < 2:
        raise ValueError("each arm needs at least two observations")
    m_c, m_t = float(c.mean()), float(t.mean())
    v_c = float(c.var(ddof=1)) / c.size
    v_t = float(t.var(ddof=1)) / t.size
    diff = m_t - m_c
    se2 = v_c + v_t
    if se2 == 0:
        return MeanResult(m_c, m_t, diff, diff, diff, 0.0, float("inf"), 1.0)
    se = math.sqrt(se2)
    df = se2**2 / (v_c**2 / (c.size - 1) + v_t**2 / (t.size - 1))
    t_stat = diff / se
    p = float(2 * stats.t.sf(abs(t_stat), df))
    q = float(stats.t.ppf(1 - alpha / 2, df))
    return MeanResult(m_c, m_t, diff, diff - q * se, diff + q * se, t_stat, df, p)
