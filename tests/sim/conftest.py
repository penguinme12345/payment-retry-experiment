"""Shared fixtures for the simulator tests."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

from retrylab.sim import generate
from retrylab.sim.schemas import SCHEMAS

ROOT = Path(os.environ.get("PROJECT_ROOT") or Path(__file__).resolve().parents[2])
CONFIG_DIR = ROOT / "config"
TABLES = tuple(SCHEMAS)


def write_config(directory: Path, **overrides: Any) -> Path:
    """Copy config/sim.yaml (+ ground truth) into ``directory`` with ``overrides`` applied."""
    directory.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load((CONFIG_DIR / "sim.yaml").read_text())
    cfg.update(overrides)
    path = directory / "sim.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    shutil.copy(CONFIG_DIR / "ground_truth.yaml", directory / "ground_truth.yaml")
    return path


def load_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    return {t: pd.read_parquet(raw_dir / f"{t}.parquet") for t in TABLES}


@pytest.fixture(scope="session")
def ground_truth() -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / "ground_truth.yaml").read_text())


@pytest.fixture(scope="session")
def small_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, int]]:
    base = tmp_path_factory.mktemp("sim_small")
    cfg = write_config(base / "config", n_customers=2000)
    counts = generate(cfg, base / "raw")
    return base / "raw", counts


@pytest.fixture(scope="session")
def small(small_run: tuple[Path, dict[str, int]]) -> dict[str, pd.DataFrame]:
    return load_tables(small_run[0])


@pytest.fixture(scope="session")
def full(tmp_path_factory: pytest.TempPathFactory) -> dict[str, pd.DataFrame]:
    """The default 50k-customer dataset, for statistical checks that need the full sample."""
    base = tmp_path_factory.mktemp("sim_full")
    generate(write_config(base / "config"), base / "raw")
    return load_tables(base / "raw")


def experiment_frame(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per experiment invoice with variant, decline code, recovery and CUPED covariate."""
    inv, att = t["raw_invoices"], t["raw_payment_attempts"]
    a = att.merge(inv[["invoice_id", "customer_id", "is_experiment_invoice"]], on="invoice_id")
    pre = a[~a.is_experiment_invoice]
    pre_rate = pre.outcome.eq("failed").groupby(pre.customer_id).mean()
    ex = a[a.is_experiment_invoice]
    a0 = ex[ex.attempt_number == 0].set_index("customer_id")
    df = pd.DataFrame(
        {
            "decline_code": a0.decline_code,
            "failed_at": a0.attempted_at,
            "is_recovered": ex.outcome.eq("succeeded").groupby(ex.customer_id).any(),
        }
    )
    df = df.join(t["raw_assignments"].set_index("customer_id").variant)
    df["pre_failed_attempt_rate"] = pre_rate.reindex(df.index).fillna(0.0)
    return df


@pytest.fixture(scope="session")
def make_config() -> Callable[..., Path]:
    """Factory: ``make_config(directory, **overrides)`` writes a sim config and returns its path."""
    return write_config


@pytest.fixture(scope="session")
def small_exp(small: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return experiment_frame(small)


@pytest.fixture(scope="session")
def full_exp(full: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return experiment_frame(full)
