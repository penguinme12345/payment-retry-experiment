"""Every statistical function vs. scipy/statsmodels reference results, within 1e-6."""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import (
    confint_proportions_2indep,
    proportion_confint,
    proportions_ztest,
)
from statsmodels.stats.weightstats import CompareMeans, DescrStatsW

from retrylab.analysis.cuped import cuped, cuped_adjust
from retrylab.analysis.means import welch_ttest
from retrylab.analysis.proportions import (
    compare_proportions,
    newcombe_diff_ci,
    two_proportion_ztest,
    wilson_interval,
)
from retrylab.analysis.segments import benjamini_hochberg
from retrylab.analysis.srm import srm_check

TOL = 1e-6

# (x_control, n_control, x_treatment, n_treatment): hand-picked, including edge-ish cases.
PROPORTION_CASES = [
    (345, 1000, 377, 1000),
    (8625, 25000, 9425, 25000),
    (56, 70, 48, 80),  # Newcombe (1998) Table II example a
    (9, 10, 3, 10),
    (0, 50, 4, 60),
    (12, 12, 10, 15),
]


@pytest.mark.parametrize("x_c,n_c,x_t,n_t", PROPORTION_CASES)
def test_wilson_matches_statsmodels(x_c: int, n_c: int, x_t: int, n_t: int) -> None:
    for x, n in ((x_c, n_c), (x_t, n_t)):
        ref = proportion_confint(x, n, alpha=0.05, method="wilson")
        assert wilson_interval(x, n) == pytest.approx(ref, abs=TOL)


@pytest.mark.parametrize("x_c,n_c,x_t,n_t", PROPORTION_CASES)
def test_newcombe_matches_statsmodels(x_c: int, n_c: int, x_t: int, n_t: int) -> None:
    ref = confint_proportions_2indep(x_t, n_t, x_c, n_c, method="newcomb", compare="diff")
    assert newcombe_diff_ci(x_c, n_c, x_t, n_t) == pytest.approx(ref, abs=TOL)


def test_newcombe_published_example() -> None:
    # Newcombe (1998), Stat Med 17:873, Table II (a): 56/70 vs 48/80 → (0.0524, 0.3339).
    low, high = newcombe_diff_ci(48, 80, 56, 70)
    assert (round(low, 4), round(high, 4)) == (0.0524, 0.3339)


@pytest.mark.parametrize("x_c,n_c,x_t,n_t", PROPORTION_CASES)
def test_ztest_matches_statsmodels(x_c: int, n_c: int, x_t: int, n_t: int) -> None:
    z_ref, p_ref = proportions_ztest([x_t, x_c], [n_t, n_c])
    z, p = two_proportion_ztest(x_c, n_c, x_t, n_t)
    assert z == pytest.approx(z_ref, abs=TOL)
    assert p == pytest.approx(p_ref, abs=TOL)


def test_compare_proportions_hand_computed() -> None:
    r = compare_proportions(345, 1000, 377, 1000)
    assert r.abs_lift == pytest.approx(0.032, abs=TOL)
    assert r.rel_lift == pytest.approx(0.032 / 0.345, abs=TOL)
    # pooled p = 0.361, se = sqrt(.361*.639*.002)
    se = np.sqrt(0.361 * 0.639 * 0.002)
    assert r.z == pytest.approx(0.032 / se, abs=TOL)
    assert r.p_value == pytest.approx(2 * stats.norm.sf(0.032 / se), abs=TOL)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_welch_matches_scipy_and_statsmodels(seed: int) -> None:
    rng = np.random.default_rng(seed)
    c = rng.exponential(10, 300) * (rng.random(300) < 0.35)
    t = rng.exponential(12, 450) * (rng.random(450) < 0.38)
    r = welch_ttest(c, t)
    ref = stats.ttest_ind(t, c, equal_var=False)
    assert r.t == pytest.approx(ref.statistic, abs=TOL)
    assert r.p_value == pytest.approx(ref.pvalue, abs=TOL)
    ci = CompareMeans(DescrStatsW(t), DescrStatsW(c)).tconfint_diff(usevar="unequal")
    assert (r.ci_low, r.ci_high) == pytest.approx(ci, abs=TOL)
    assert r.abs_lift == pytest.approx(t.mean() - c.mean(), abs=TOL)


def test_welch_hand_computed() -> None:
    c, t = [1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0, 10.0]
    r = welch_ttest(c, t)
    # means 2.5, 6; vars 5/3, 10; se² = 5/12 + 2
    se = np.sqrt(5 / 12 + 2)
    df = (5 / 12 + 2) ** 2 / ((5 / 12) ** 2 / 3 + 2**2 / 4)
    assert r.abs_lift == pytest.approx(3.5, abs=TOL)
    assert r.t == pytest.approx(3.5 / se, abs=TOL)
    assert r.df == pytest.approx(df, abs=TOL)


@pytest.mark.parametrize("n_c,n_t", [(25000, 25000), (25200, 24800), (25000, 24250), (10, 30)])
def test_srm_matches_scipy(n_c: int, n_t: int) -> None:
    ref = stats.chisquare([n_c, n_t])
    r = srm_check(n_c, n_t)
    assert r.chi2 == pytest.approx(ref.statistic, abs=TOL)
    assert r.p_value == pytest.approx(ref.pvalue, abs=TOL)
    assert r.passed == (ref.pvalue >= 0.001)


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_bh_matches_statsmodels(seed: int) -> None:
    p = np.random.default_rng(seed).beta(0.5, 2, 18)
    p[3] = p[7]  # ties
    ref = multipletests(p, alpha=0.05, method="fdr_bh")[1]
    np.testing.assert_allclose(benjamini_hochberg(p), ref, atol=TOL)


def test_bh_hand_computed() -> None:
    np.testing.assert_allclose(
        benjamini_hochberg([0.01, 0.04, 0.03, 0.20]), [0.04, 0.04 * 4 / 3, 0.04 * 4 / 3, 0.20]
    )


def test_cuped_theta_is_ols_slope_and_lift_matches_welch() -> None:
    rng = np.random.default_rng(7)
    n = 2000
    x = rng.normal(size=n)
    is_t = rng.random(n) < 0.5
    y = 0.5 * x + rng.normal(size=n) + 0.1 * is_t
    y_adj, theta = cuped_adjust(y, x)
    assert theta == pytest.approx(stats.linregress(x, y).slope, abs=TOL)
    np.testing.assert_allclose(y_adj, y - theta * (x - x.mean()), atol=TOL)
    r = cuped(y, x, is_t)
    ref = stats.ttest_ind(y_adj[is_t], y_adj[~is_t], equal_var=False)
    ci = CompareMeans(DescrStatsW(y_adj[is_t]), DescrStatsW(y_adj[~is_t])).tconfint_diff(
        usevar="unequal"
    )
    assert r.p_value == pytest.approx(ref.pvalue, abs=TOL)
    assert (r.ci_low, r.ci_high) == pytest.approx(ci, abs=TOL)
    vr = 100 * (1 - np.var(y_adj, ddof=1) / np.var(y, ddof=1))
    assert r.variance_reduction_pct == pytest.approx(vr, abs=TOL)
