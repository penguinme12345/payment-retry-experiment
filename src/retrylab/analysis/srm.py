"""Sample-ratio-mismatch check: χ² goodness-of-fit against the planned 50/50 split."""

from __future__ import annotations

from dataclasses import dataclass

from scipy import stats

SRM_THRESHOLD = 0.001


@dataclass(frozen=True)
class SrmResult:
    chi2: float
    p_value: float
    passed: bool
    threshold: float


def srm_check(n_control: int, n_treatment: int, threshold: float = SRM_THRESHOLD) -> SrmResult:
    """χ² test of ``[n_control, n_treatment]`` against equal expected counts.

    ``passed`` is ``p_value >= threshold``.
    """
    total = n_control + n_treatment
    if total == 0:
        raise ValueError("no units to check")
    expected = total / 2.0
    chi2 = ((n_control - expected) ** 2 + (n_treatment - expected) ** 2) / expected
    p_value = float(stats.chi2.sf(chi2, df=1))
    return SrmResult(float(chi2), p_value, p_value >= threshold, threshold)
