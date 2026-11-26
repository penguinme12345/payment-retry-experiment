"""Property tests: A/A coverage, SRM detection, CUPED variance reduction, planted effects."""

from __future__ import annotations

import numpy as np
import pytest
from fixtures.make_fixture_db import make_invoices

from retrylab.analysis.cuped import cuped
from retrylab.analysis.io import DEFAULT_POWER_ANALYSIS
from retrylab.analysis.proportions import compare_proportions
from retrylab.analysis.run import build_results
from retrylab.analysis.srm import srm_check


def test_aa_ci_covers_zero_in_at_least_93_percent_of_runs() -> None:
    covered = 0
    for seed in range(200):
        df = make_invoices(n=4000, seed=seed, effects={})
        is_t = (df["variant"] == "treatment").to_numpy()
        y = df["is_recovered"].to_numpy()
        r = compare_proportions(
            int(y[~is_t].sum()), int((~is_t).sum()), int(y[is_t].sum()), int(is_t.sum())
        )
        covered += r.ci_low <= 0 <= r.ci_high
    assert covered / 200 >= 0.93


def test_srm_fixture_fails() -> None:
    df = make_invoices(n=20000, seed=1, effects={}, treatment_share=0.47)
    n_t = int((df["variant"] == "treatment").sum())
    assert not srm_check(len(df) - n_t, n_t).passed
    res = build_results(df, DEFAULT_POWER_ANALYSIS)
    assert res["srm"]["passed"] is False
    assert res["recommendation"]["decision"] == "do_not_ship"
    assert "invalid experiment" in res["recommendation"]["rationale"]


def test_balanced_fixture_passes_srm() -> None:
    df = make_invoices(n=20000, seed=1, effects={})
    n_t = int((df["variant"] == "treatment").sum())
    assert srm_check(len(df) - n_t, n_t).passed


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_cuped_variance_reduction_with_rho_half(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = 20000
    x = rng.normal(size=n)
    y = 0.5 * x + np.sqrt(1 - 0.25) * rng.normal(size=n)  # corr(x, y) = 0.5
    is_t = rng.random(n) < 0.5
    r = cuped(y, x, is_t)
    assert r.variance_reduction_pct == pytest.approx(25.0, abs=5.0)


def test_planted_segment_effect_is_recovered() -> None:
    df = make_invoices(n=50000, seed=3)  # +5pp in insufficient_funds only
    res = build_results(df, DEFAULT_POWER_ANALYSIS)
    seg = {(s["dimension"], s["value"]): s for s in res["segments"]}
    target = seg[("initial_decline_code", "insufficient_funds")]
    assert target["significant_adj"]
    assert target["ci_low"] <= 0.05 <= target["ci_high"]
    for dim in ("initial_decline_code",):
        for (d, v), s in seg.items():
            if d == dim and v != "insufficient_funds":
                assert not s["significant_adj"], (d, v)
    # 40% of invoices get +5pp → overall ≈ +2pp
    assert res["primary"]["ci_low"] <= 0.02 <= res["primary"]["ci_high"]


def test_cuped_narrows_ci_on_fixture() -> None:
    df = make_invoices(n=20000, seed=4, covariate_slope=2.0)
    res = build_results(df, DEFAULT_POWER_ANALYSIS)
    raw_w = res["primary"]["ci_high"] - res["primary"]["ci_low"]
    cu_w = res["cuped"]["ci_high"] - res["cuped"]["ci_low"]
    assert res["cuped"]["variance_reduction_pct"] > 0
    assert cu_w < raw_w
