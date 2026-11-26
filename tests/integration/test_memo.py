"""Memo rendering against hand-written fixtures covering every decision branch."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from retrylab.reporting import render_memo, write_memo
from retrylab.reporting.__main__ import main as memo_main
from retrylab.reporting.context import build_context

FIXTURES = Path(__file__).parent / "fixtures"
TEMPLATE = Path(__file__).parents[2] / "src" / "retrylab" / "reporting" / "templates" / "memo.md.j2"
BRANCHES = ["ship", "ship_segmented", "do_not_ship", "do_not_ship_srm", "do_not_ship_guardrail"]
SECTIONS = [
    "## TL;DR",
    "## What we tested and why",
    "## Results",
    "## Where it works",
    "## Guardrails",
    "## Recommendation and next steps",
    "## Caveats",
]


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def power() -> dict:
    return _load("power_analysis.json")


@pytest.mark.parametrize("branch", BRANCHES)
def test_renders_cleanly(branch: str, power: dict) -> None:
    memo = render_memo(_load(f"results_{branch}.json"), power)
    assert "{{" not in memo and "{%" not in memo and "}}" not in memo
    assert "None" not in memo
    assert "nan" not in memo.lower().split()
    assert "\n\n\n" not in memo
    for s in SECTIONS:
        assert s in memo, f"{branch}: missing {s}"
    words = len(memo.split())
    assert 350 <= words <= 700, f"{branch}: {words} words"


@pytest.mark.parametrize(
    ("branch", "phrases"),
    [
        ("ship", ["recommend shipping smart retry timing to all customers", "**Decision: ship.**"]),
        (
            "ship_segmented",
            [
                "only for insufficient-funds declines",
                "**Decision: ship to insufficient-funds declines.**",
                "from the shipped segments",
            ],
        ),
        ("do_not_ship", ["not a reliable improvement", "**Decision: do not ship.**"]),
        ("do_not_ship_srm", ["Sample-ratio check failed", "cannot be trusted"]),
        ("do_not_ship_guardrail", ["**Breached:**", "rules out shipping"]),
    ],
)
def test_branch_narrative(branch: str, phrases: list[str], power: dict) -> None:
    memo = render_memo(_load(f"results_{branch}.json"), power)
    for p in phrases:
        assert p in memo, f"{branch}: expected {p!r}"


def test_do_not_ship_has_no_impact_claim(power: dict) -> None:
    for branch in ["do_not_ship", "do_not_ship_srm", "do_not_ship_guardrail"]:
        memo = render_memo(_load(f"results_{branch}.json"), power)
        assert "Estimated impact" not in memo


def test_numbers_come_from_results(power: dict) -> None:
    memo = render_memo(_load("results_ship.json"), power)
    assert "33.6% to 37.1%" in memo  # control / treatment
    assert "+3.6pp (95% CI [2.7pp, 4.4pp])" in memo
    assert "$6.5M a year" in memo
    assert "Customers declined for insufficient funds recovered 6.8pp more often" in memo
    assert "8.1%" in memo  # CUPED variance reduction
    assert "8,983" in memo and "25,000" in memo  # power analysis


def test_numbers_follow_inputs(power: dict) -> None:
    results = _load("results_ship.json")
    results["primary"].update(control=0.4, treatment=0.45, abs_lift=0.05)
    results["revenue_impact"]["annualized_incremental_revenue_usd"] = 48_321.0
    memo = render_memo(results, power)
    assert "40.0% to 45.0%" in memo and "+5.0pp" in memo and "$48,300" in memo


def test_template_has_no_hardcoded_numbers() -> None:
    text = TEMPLATE.read_text()
    # Strip Jinja expressions/statements, then look for any digits left in the prose. The schedule
    # description ("day 1, 3, 5, 7", "four retries", "seven days") is the experiment design from
    # contract C2, written in words or listed explicitly here.
    prose = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", text, flags=re.DOTALL)
    prose = prose.replace("day 1, 3, 5, 7", "")
    assert not re.search(r"\d", prose), re.findall(r".{20}\d.{20}", prose)


def test_segment_sentences_rank_by_evidence(power: dict) -> None:
    ctx = build_context(_load("results_ship.json"), power)
    keys = [(s.p_adj_value, -s.abs_lift) for s in ctx.positive_segments]
    assert keys == sorted(keys)
    assert ctx.positive_segments[0].value == "insufficient_funds"
    assert ctx.n_positive_segments == 3


def test_negative_segment_reported(power: dict) -> None:
    results = _load("results_ship_segmented.json")
    row = next(s for s in results["segments"] if s["value"] == "prepaid")
    row.update(abs_lift=-0.03, treatment_rate=row["control_rate"] - 0.03, significant_adj=True)
    memo = render_memo(results, power)
    assert "did worse for some customers" in memo
    assert "Customers paying with a prepaid card recovered 3.0pp less often" in memo


def test_unknown_decision_rejected(power: dict) -> None:
    results = _load("results_ship.json")
    results["recommendation"]["decision"] = "maybe"
    with pytest.raises(ValueError):
        render_memo(results, power)


def test_figures_embedded_when_present(tmp_path: Path, power: dict) -> None:
    figs = tmp_path / "reports" / "figures"
    figs.mkdir(parents=True)
    (figs / "segment_forest.png").write_bytes(b"\x89PNG")
    (figs / "lift_overall.png").write_bytes(b"\x89PNG")
    out = tmp_path / "docs" / "memo.md"
    memo = write_memo(FIXTURES / "results_ship.json", FIXTURES / "power_analysis.json", out, figs)
    assert out.read_text() == memo
    assert "## Figures" in memo
    assert "](../reports/figures/lift_overall.png)" in memo
    assert memo.index("lift_overall.png") < memo.index("segment_forest.png")
    assert "recovery_by_day.png" not in memo


def test_cli_resolves_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "reports").mkdir()
    for src, dst in [("results_ship.json", "results.json"), ("power_analysis.json",) * 2]:
        (tmp_path / "reports" / dst).write_text((FIXTURES / src).read_text())
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    assert memo_main([]) == 0
    assert (tmp_path / "docs" / "memo.md").is_file()
    assert "wrote" in capsys.readouterr().out


def test_render_is_deterministic(power: dict) -> None:
    r = _load("results_ship_segmented.json")
    assert render_memo(r, power) == render_memo(r, power)
