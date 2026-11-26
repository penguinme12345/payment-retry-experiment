"""SRM toggle: drop 3% of treatment customers after assignment."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from scipy.stats import chisquare

from retrylab.sim import generate, simulate
from retrylab.sim.config import load_config

SRM_THRESHOLD = 0.001  # contract C6 srm.threshold


def _srm_p(variants: pd.Series) -> float:
    counts = variants.value_counts().reindex(["control", "treatment"]).to_numpy()
    return float(chisquare(counts).pvalue)


def test_srm_drop_only_removes_treatment_customers(
    tmp_path: Path, small: dict[str, pd.DataFrame], make_config: Callable[..., Path]
) -> None:
    generate(make_config(tmp_path / "config", n_customers=2000, inject_srm=True), tmp_path / "raw")
    srm = pd.read_parquet(tmp_path / "raw" / "raw_assignments.parquet").set_index("customer_id")
    base = small["raw_assignments"].set_index("customer_id")
    dropped = base.index.difference(srm.index)
    assert (base.loc[dropped, "variant"] == "treatment").all()
    n_treat = (base.variant == "treatment").sum()
    assert len(dropped) == round(0.03 * n_treat)
    # everything else is unchanged
    pd.testing.assert_frame_equal(srm, base.drop(dropped))
    inv = pd.read_parquet(tmp_path / "raw" / "raw_invoices.parquet")
    assert not inv.customer_id.isin(dropped).any()


@pytest.mark.slow
@pytest.mark.parametrize(("inject", "should_pass"), [(False, True), (True, False)])
def test_srm_chi_square(
    tmp_path: Path, make_config: Callable[..., Path], inject: bool, should_pass: bool
) -> None:
    # 200k customers so a 3% treatment drop is reliably detectable at p < 0.001.
    cfg = load_config(make_config(tmp_path, n_customers=200_000, inject_srm=inject))
    variants = simulate(cfg)["raw_assignments"].column("variant").to_pandas()
    assert (_srm_p(variants) >= SRM_THRESHOLD) is should_pass


def test_default_config_passes_srm(full: dict[str, pd.DataFrame]) -> None:
    assert _srm_p(full["raw_assignments"].variant) >= SRM_THRESHOLD
