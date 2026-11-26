"""End-to-end: fixture warehouse → results.json (schema-valid, deterministic) + figures."""

from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import pytest
from fixtures.make_fixture_db import make_invoices, write_fixture_db

from retrylab.analysis.__main__ import main
from retrylab.analysis.io import DEFAULT_POWER_ANALYSIS, read_power_analysis
from retrylab.analysis.run import build_results
from retrylab.analysis.schema import Results

FROZEN = "2026-04-15T12:00:00Z"
C6_KEYS = [
    "experiment_id",
    "generated_at",
    "n_control",
    "n_treatment",
    "srm",
    "primary",
    "cuped",
    "secondary",
    "guardrails",
    "segments",
    "revenue_impact",
    "recommendation",
]


def _decimals_ok(obj: object) -> bool:
    if isinstance(obj, float):
        return round(obj, 6) == obj
    if isinstance(obj, dict):
        return all(_decimals_ok(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_decimals_ok(v) for v in obj)
    return True


@pytest.fixture(scope="module")
def outputs(fixture_db: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("reports")
    with pytest.warns(UserWarning, match="C5 default"):
        assert main(["--db", str(fixture_db), "--out", str(out), "--frozen-time", FROZEN]) == 0
    return out


def test_results_validate_against_c6(outputs: Path) -> None:
    data = json.loads((outputs / "results.json").read_text())
    Results.model_validate(data)
    assert list(data) == C6_KEYS
    assert data["generated_at"] == FROZEN
    assert data["n_control"] + data["n_treatment"] == 4000
    assert _decimals_ok(data)
    assert len(data["segments"]) == 8 + 3 + 3 + 4
    assert [g["metric"] for g in data["guardrails"]] == [
        "billing_ticket_rate",
        "involuntary_churn_rate",
    ]


def test_output_is_deterministic(fixture_db: Path, outputs: Path, tmp_path: Path) -> None:
    with pytest.warns(UserWarning):
        main(["--db", str(fixture_db), "--out", str(tmp_path), "--frozen-time", FROZEN])
    assert (tmp_path / "results.json").read_bytes() == (outputs / "results.json").read_bytes()
    for name in ("lift_overall.png", "segment_forest.png", "recovery_by_day.png"):
        assert (tmp_path / "figures" / name).read_bytes() == (
            outputs / "figures" / name
        ).read_bytes()


@pytest.mark.parametrize("name", ["lift_overall.png", "segment_forest.png", "recovery_by_day.png"])
def test_figures_exist_and_are_nonempty(outputs: Path, name: str) -> None:
    from PIL import Image

    path = outputs / "figures" / name
    assert path.stat().st_size > 10_000
    with Image.open(path) as im:
        assert im.size == (1200, 750)  # 8×5 in at 150 dpi
        assert len(set(im.convert("L").tobytes())) > 10  # not blank


def test_power_analysis_is_read_when_present(tmp_path: Path) -> None:
    pa = dict(DEFAULT_POWER_ANALYSIS, alpha=0.1)
    pa["guardrails"] = [{"metric": "billing_ticket_rate", "max_acceptable_increase_abs": 0.01}]
    (tmp_path / "power_analysis.json").write_text(json.dumps(pa))
    got = read_power_analysis(tmp_path / "power_analysis.json")
    assert got["alpha"] == 0.1 and len(got["guardrails"]) == 1
    res = build_results(make_invoices(seed=2), got)
    assert res["primary"]["ci_level"] == 0.9
    assert res["guardrails"][0]["threshold_abs"] == 0.01


def test_guardrail_breach_flows_to_decision() -> None:
    df = make_invoices(n=20000, seed=5, billing_rates=(0.03, 0.06))
    res = build_results(df, DEFAULT_POWER_ANALYSIS)
    g = res["guardrails"][0]
    assert g["breached"] and g["ci_low"] > g["threshold_abs"]
    assert res["recommendation"]["decision"] == "do_not_ship"


def test_warehouse_opened_read_only(fixture_db: Path) -> None:
    from retrylab.analysis.io import read_invoices

    df = read_invoices(fixture_db)
    assert len(df) == 4000
    with duckdb.connect(str(fixture_db)) as con:  # no lingering lock
        assert con.execute("select count(*) from fct_experiment_invoices").fetchone()[0] == 4000


def test_full_run_on_50k_rows_under_30s(tmp_path: Path) -> None:
    db = write_fixture_db(make_invoices(n=50000, seed=9), tmp_path / "wh.duckdb")
    start = time.perf_counter()
    with pytest.warns(UserWarning):
        main(["--db", str(db), "--out", str(tmp_path / "out"), "--frozen-time", FROZEN])
    assert time.perf_counter() - start < 30
    res = json.loads((tmp_path / "out" / "results.json").read_text())
    assert res["n_control"] + res["n_treatment"] == 50000
