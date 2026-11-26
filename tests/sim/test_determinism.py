from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from retrylab.sim import generate
from retrylab.sim.schemas import SCHEMAS


def _hashes(raw_dir: Path) -> dict[str, str]:
    return {t: hashlib.sha256((raw_dir / f"{t}.parquet").read_bytes()).hexdigest() for t in SCHEMAS}


def test_same_seed_gives_identical_files(
    tmp_path: Path, small_run: tuple[Path, dict[str, int]], make_config: Callable[..., Path]
) -> None:
    generate(make_config(tmp_path / "config", n_customers=2000), tmp_path / "raw")
    assert _hashes(tmp_path / "raw") == _hashes(small_run[0])


def test_different_seed_changes_output(
    tmp_path: Path, small_run: tuple[Path, dict[str, int]], make_config: Callable[..., Path]
) -> None:
    generate(make_config(tmp_path / "config", n_customers=2000, seed=7), tmp_path / "raw")
    assert _hashes(tmp_path / "raw") != _hashes(small_run[0])
