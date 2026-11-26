from __future__ import annotations

import math

import pytest
from scipy.stats import norm

from retrylab.design.power import (
    achieved_power,
    cohens_h,
    mde_for_n,
    required_n_per_arm,
    required_n_per_arm_continuous,
    statsmodels_n_per_arm,
)

CASES = [
    # (p_baseline, mde_abs, alpha, power, two_sided)
    (0.345, 0.02, 0.05, 0.8, True),
    (0.345, 0.01, 0.05, 0.8, True),
    (0.10, 0.02, 0.05, 0.9, True),
    (0.50, 0.05, 0.01, 0.8, True),
    (0.15, 0.03, 0.05, 0.8, False),
    (0.45, -0.02, 0.05, 0.8, True),
]


def hand_formula(p1: float, d: float, alpha: float, power: float, two_sided: bool) -> float:
    p2 = p1 + d
    pb = (p1 + p2) / 2
    za = norm.ppf(1 - alpha / 2) if two_sided else norm.ppf(1 - alpha)
    zb = norm.ppf(power)
    num = za * math.sqrt(2 * pb * (1 - pb)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    return num**2 / d**2


@pytest.mark.parametrize("case", CASES)
def test_required_n_matches_hand_formula(case):
    n = required_n_per_arm(*case)
    hand = hand_formula(*case)
    assert n == math.ceil(hand)
    assert abs(n - hand) / hand < 0.01


def test_known_value_for_design_inputs():
    # (1.959964·√(2·0.355·0.645) + 0.841621·√(0.345·0.655 + 0.365·0.635))² / 0.02² ≈ 8984.3
    assert required_n_per_arm(0.345, 0.02) == 8985


@pytest.mark.parametrize("case", CASES)
def test_required_n_agrees_with_statsmodels(case):
    n = required_n_per_arm(*case)
    ref = statsmodels_n_per_arm(*case)
    assert abs(n - ref) / ref < 0.02


@pytest.mark.parametrize("case", CASES)
def test_mde_round_trip(case):
    p, d, alpha, power, two_sided = case
    n = required_n_per_arm(p, d, alpha, power, two_sided)
    mde = mde_for_n(p, n, alpha, power, two_sided)
    if d > 0:
        assert abs(mde - d) < 1e-4
        assert mde <= d + 1e-12  # n was rounded up, so the MDE can only shrink


def test_mde_exact_inverse_of_continuous_n():
    for d in (0.005, 0.0123, 0.02, 0.05):
        n = required_n_per_arm_continuous(0.345, d)
        assert mde_for_n(0.345, n) == pytest.approx(d, abs=1e-9)


def test_mde_decreases_with_n():
    mdes = [mde_for_n(0.345, n) for n in (2_500, 5_000, 10_000, 25_000, 100_000)]
    assert all(a > b for a, b in zip(mdes, mdes[1:], strict=False))
    # Rule of thumb: quadrupling n halves the MDE.
    assert mde_for_n(0.345, 40_000) / mde_for_n(0.345, 10_000) == pytest.approx(0.5, rel=0.02)


@pytest.mark.parametrize("case", CASES)
def test_achieved_power_at_required_n(case):
    p, d, alpha, power, two_sided = case
    n = required_n_per_arm(p, d, alpha, power, two_sided)
    pw = achieved_power(p, d, n, alpha, two_sided)
    assert power - 1e-6 <= pw < power + 0.005


def test_achieved_power_monotone_and_bounded():
    pws = [achieved_power(0.345, 0.02, n) for n in (500, 2_000, 8_985, 25_000)]
    assert all(0 < a < b <= 1 for a, b in zip(pws, pws[1:], strict=False))
    # With a negligible effect, two-sided power collapses to alpha.
    assert achieved_power(0.345, 1e-7, 1_000) == pytest.approx(0.05, abs=1e-4)


def test_achieved_power_matches_statsmodels_cohens_h():
    from statsmodels.stats.power import NormalIndPower

    h = abs(cohens_h(0.345, 0.365))
    ref = NormalIndPower().power(h, nobs1=25_000, alpha=0.05, ratio=1.0)
    assert achieved_power(0.345, 0.02, 25_000) == pytest.approx(ref, abs=0.002)


def test_one_sided_needs_fewer_units():
    assert required_n_per_arm(0.345, 0.02, two_sided=False) < required_n_per_arm(0.345, 0.02)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"p_baseline": 0.0, "mde_abs": 0.02},
        {"p_baseline": 1.2, "mde_abs": 0.02},
        {"p_baseline": 0.345, "mde_abs": 0.0},
        {"p_baseline": 0.99, "mde_abs": 0.02},
        {"p_baseline": 0.345, "mde_abs": 0.02, "alpha": 0.0},
        {"p_baseline": 0.345, "mde_abs": 0.02, "power": 1.0},
    ],
)
def test_invalid_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        required_n_per_arm(**kwargs)


def test_mde_for_tiny_n_raises():
    with pytest.raises(ValueError):
        mde_for_n(0.345, 1)
