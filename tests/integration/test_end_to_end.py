"""End-to-end pipeline test (PRD-F §2.1). Runs ``make all`` at 5k customers in a scratch copy.

Skips until every upstream workstream (B–E) has landed its entry point. This is the one place
outside ``tests/sim`` allowed to read ``config/ground_truth.yaml`` (contract C7).
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = {
    "simulator (A)": ROOT / "src/retrylab/sim/__main__.py",
    "dbt project (B)": ROOT / "dbt/dbt_project.yml",
    "power analysis (C)": ROOT / "src/retrylab/design/__main__.py",
    "analysis (D)": ROOT / "src/retrylab/analysis/__main__.py",
    "Power BI export (E)": ROOT / "app/export.py",
}
_missing = [name for name, path in REQUIRED.items() if not path.exists()]

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(bool(_missing), reason=f"upstream not merged yet: {', '.join(_missing)}"),
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
]

_IGNORE = shutil.ignore_patterns(
    ".git",
    ".venv",
    "__pycache__",
    "*.parquet",
    "*.duckdb",
    "*.duckdb.wal",
    "target",
    "logs",
    "dbt_packages",
    ".pytest_cache",
    ".ruff_cache",
    "*.egg-info",
)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PROJECT_ROOT": str(cwd), "PYTHON": sys.executable}
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, (
        f"{' '.join(cmd)} failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    )
    return proc


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("e2e") / "retrylab"
    shutil.copytree(ROOT, work, ignore=_IGNORE)
    _run(
        ["make", "clean", "all", "SIM_CONFIG=config/sim.ci.yaml", f"PYTHON={sys.executable}"], work
    )
    return work


@pytest.fixture(scope="module")
def results(pipeline: Path) -> dict:
    return json.loads((pipeline / "reports/results.json").read_text())


def _blended_true_lift(root: Path) -> float:
    gt = yaml.safe_load((root / "config/ground_truth.yaml").read_text())
    sim = yaml.safe_load((root / "config/sim.ci.yaml").read_text())
    mix, payday = sim["decline_mix"], sim["payday_known_rate"]
    lift = 0.0
    for code, share in mix.items():
        effect = gt["treatment_lift_abs"][code]
        if code == "insufficient_funds":
            effect += gt["payday_known_extra_lift_abs"] * payday
        lift += share * effect
    return lift


def test_results_validate_against_schema(results: dict) -> None:
    from pydantic import BaseModel

    schema = importlib.import_module("retrylab.analysis.schema")
    models = [
        m
        for m in vars(schema).values()
        if isinstance(m, type) and issubclass(m, BaseModel) and "recommendation" in m.model_fields
    ]
    assert models, "no top-level results model found in retrylab.analysis.schema"
    models[0].model_validate(results)


def test_srm_passes(results: dict) -> None:
    assert results["srm"]["passed"] is True


def test_overall_ci_contains_true_effect(results: dict, pipeline: Path) -> None:
    true_lift = _blended_true_lift(pipeline)
    p = results["primary"]
    assert p["ci_low"] <= true_lift <= p["ci_high"], (true_lift, p["ci_low"], p["ci_high"])


def _segment(results: dict, value: str) -> dict:
    return next(
        s
        for s in results["segments"]
        if s["dimension"] == "initial_decline_code" and s["value"] == value
    )


def test_insufficient_funds_significant_and_positive(results: dict) -> None:
    seg = _segment(results, "insufficient_funds")
    assert seg["significant_adj"] is True and seg["abs_lift"] > 0


def test_expired_card_not_significant(results: dict) -> None:
    assert _segment(results, "expired_card")["significant_adj"] is False


def test_memo_rendered(pipeline: Path) -> None:
    memo = (pipeline / "docs/memo.md").read_text()
    assert memo.strip()
    assert "{{" not in memo and "None" not in memo


def _frozen_time_args(cwd: Path) -> list[str]:
    """``--frozen-time`` may be a bare flag or take a timestamp; support both."""
    help_text = _run([sys.executable, "-m", "retrylab.analysis", "--help"], cwd).stdout
    if "--frozen-time FROZEN" in help_text or "--frozen-time TIME" in help_text:
        return ["--frozen-time", "2026-04-15T12:00:00Z"]
    return ["--frozen-time"]


def test_reproducible_results(pipeline: Path, tmp_path: Path) -> None:
    frozen = _frozen_time_args(pipeline)
    outs = []
    for i in range(2):
        out = tmp_path / f"run{i}"
        out.mkdir()
        _run(
            [
                sys.executable,
                "-m",
                "retrylab.analysis",
                "--db",
                "data/warehouse.duckdb",
                "--out",
                str(out),
                *frozen,
            ],
            pipeline,
        )
        outs.append((out / "results.json").read_bytes())
    assert outs[0] == outs[1]
