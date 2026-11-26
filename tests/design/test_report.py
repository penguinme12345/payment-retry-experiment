"""C5 contract checks for ``reports/power_analysis.json`` and the CLI."""

from __future__ import annotations

import hashlib
import json

import pytest

from retrylab.design.__main__ import main
from retrylab.design.power import mde_for_n, required_n_per_arm
from retrylab.design.report import DesignInputs, blended_baseline, build_power_analysis

# Keys and types from 01_CONTRACTS.md § C5.
C5_TYPES: dict[str, type | tuple[type, ...]] = {
    "experiment_id": str,
    "primary_metric": str,
    "baseline_rate": float,
    "mde_abs": float,
    "alpha": float,
    "power": float,
    "two_sided": bool,
    "required_n_per_arm": int,
    "planned_n_per_arm": int,
    "achieved_power_at_mde": float,
    "mde_curve": list,
    "guardrails": list,
}


def validate_c5(payload: dict) -> None:
    for key, typ in C5_TYPES.items():
        assert key in payload, f"missing C5 key {key}"
        val = payload[key]
        if typ is float:
            assert isinstance(val, float) and not isinstance(val, bool), key
        elif typ is int:
            assert isinstance(val, int) and not isinstance(val, bool), key
        else:
            assert isinstance(val, typ), key
    for pt in payload["mde_curve"]:
        assert set(pt) == {"n_per_arm", "mde_abs"}
        assert isinstance(pt["n_per_arm"], int) and isinstance(pt["mde_abs"], float)
    for g in payload["guardrails"]:
        assert set(g) == {"metric", "max_acceptable_increase_abs"}
        assert isinstance(g["metric"], str) and isinstance(g["max_acceptable_increase_abs"], float)


@pytest.fixture(scope="module")
def payload() -> dict:
    return build_power_analysis()


def test_payload_matches_c5(payload):
    validate_c5(payload)
    assert payload["experiment_id"] == "retry_timing_v1"
    assert payload["primary_metric"] == "recovery_rate"
    assert payload["baseline_rate"] == 0.345
    assert payload["mde_abs"] == 0.02
    assert payload["alpha"] == 0.05
    assert payload["power"] == 0.8
    assert payload["two_sided"] is True
    assert payload["planned_n_per_arm"] == 25_000


def test_payload_values(payload):
    assert payload["required_n_per_arm"] == required_n_per_arm(0.345, 0.02)
    assert payload["required_n_per_arm"] < payload["planned_n_per_arm"]
    assert 0.99 < payload["achieved_power_at_mde"] <= 1.0
    assert [pt["n_per_arm"] for pt in payload["mde_curve"]] == [
        2_500,
        5_000,
        10_000,
        15_000,
        20_000,
        25_000,
    ]
    for pt in payload["mde_curve"]:
        assert pt["mde_abs"] == pytest.approx(mde_for_n(0.345, pt["n_per_arm"]), abs=5e-5)
    assert payload["guardrails"] == [
        {"metric": "billing_ticket_rate", "max_acceptable_increase_abs": 0.005},
        {"metric": "involuntary_churn_rate", "max_acceptable_increase_abs": 0.0},
    ]


def test_baseline_is_blended_decline_mix(payload):
    comps = payload["baseline_components"]
    assert sum(c["share"] for c in comps) == pytest.approx(1.0)
    assert sum(c["share"] * c["recovery_rate"] for c in comps) == pytest.approx(0.345)
    assert blended_baseline(DesignInputs().decline_mix) == pytest.approx(0.345)


def test_segment_mde_rows(payload):
    rows = payload["segment_mde"]
    dims = {r["dimension"] for r in rows}
    assert dims == {"initial_decline_code", "plan_tier", "card_funding", "country"}
    assert len(rows) == 4 + 3 + 3 + 8
    for dim in dims:
        assert sum(r["share"] for r in rows if r["dimension"] == dim) == pytest.approx(1.0)
    ins = next(r for r in rows if r["value"] == "insufficient_funds")
    assert ins["mde_abs"] < payload["mde_abs"]  # the key segment is powered for the target MDE


def test_inconsistent_baseline_rejected():
    with pytest.raises(ValueError):
        build_power_analysis(DesignInputs(baseline_rate=0.30))


def test_cli_writes_json_and_figure_deterministically(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    hashes = []
    for _ in range(2):
        assert main(["--out", "reports/power_analysis.json"]) == 0
        js = tmp_path / "reports" / "power_analysis.json"
        png = tmp_path / "reports" / "figures" / "power_curve.png"
        assert js.exists() and png.exists() and png.stat().st_size > 10_000
        validate_c5(json.loads(js.read_text()))
        hashes.append(
            (
                hashlib.sha256(js.read_bytes()).hexdigest(),
                hashlib.sha256(png.read_bytes()).hexdigest(),
            )
        )
    assert hashes[0] == hashes[1]
