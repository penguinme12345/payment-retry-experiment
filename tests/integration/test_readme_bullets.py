"""Resume bullets and generated README blocks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from retrylab.reporting.bullets import make_bullets
from retrylab.reporting.readme import blocks, fill

FIXTURES = Path(__file__).parent / "fixtures"
BRANCHES = ["ship", "ship_segmented", "do_not_ship", "do_not_ship_srm", "do_not_ship_guardrail"]


def _load(branch: str) -> dict:
    return json.loads((FIXTURES / f"results_{branch}.json").read_text())


@pytest.mark.parametrize("branch", BRANCHES)
def test_three_short_bullets_with_numbers(branch: str) -> None:
    bullets = make_bullets(_load(branch))
    assert len(bullets) == 3
    for b in bullets:
        assert len(b) < 160, b
        assert any(ch.isdigit() for ch in b), b
        assert "None" not in b


def test_bullets_use_results_numbers() -> None:
    b = make_bullets(_load("ship"))
    assert "50,000-customer" in b[0] and "+3.6pp" in b[0]
    assert "8.1%" in b[1] and "3 of 18" in b[1]
    assert "$6.5M/yr" in b[2] and "full launch" in b[2]


def test_fill_replaces_only_marked_blocks() -> None:
    readme = (
        "intro\n<!-- BEGIN:headline -->\nold\n<!-- END:headline -->\n"
        "mid\n<!-- BEGIN:bullets -->\n_TBD_\n<!-- END:bullets -->\nend\n"
    )
    out = fill(readme, blocks(_load("ship")))
    assert out.startswith("intro\n") and out.endswith("end\n") and "\nmid\n" in out
    assert "old" not in out and "_TBD_" not in out
    assert "33.6% → 37.1%" in out
    assert out.count("\n- ") == 3
    assert fill(out, blocks(_load("ship"))) == out  # idempotent


def test_key_results_table() -> None:
    table = blocks(_load("ship_segmented"))["key-results"]
    assert "| Decision | Ship to targeted segments |" in table
    assert "Customers declined for insufficient funds" in table
