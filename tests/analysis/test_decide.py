"""One test per decision-rule branch, plus revenue impact for each scope."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from retrylab.analysis.decide import DO_NOT_SHIP, SHIP, SHIP_SEGMENTED, decide
from retrylab.analysis.guardrails import is_breached
from retrylab.analysis.impact import revenue_impact


def seg(dim: str, value: str, lift: float, sig: bool) -> dict[str, Any]:
    return {"dimension": dim, "value": value, "abs_lift": lift, "significant_adj": sig}


OK_GUARDS = [{"metric": "billing_ticket_rate", "breached": False}]
BAD_GUARDS = [{"metric": "billing_ticket_rate", "breached": True}]
POS = seg("initial_decline_code", "insufficient_funds", 0.07, True)
NEG = seg("country", "DE", -0.04, True)
NULL = seg("country", "US", 0.01, False)


def test_srm_fail_overrides_everything() -> None:
    d = decide(False, True, 0.03, OK_GUARDS, [POS])
    assert d.decision == DO_NOT_SHIP
    assert "invalid experiment" in d.rationale


def test_guardrail_breach_blocks_ship() -> None:
    d = decide(True, True, 0.03, BAD_GUARDS, [POS])
    assert d.decision == DO_NOT_SHIP
    assert "billing_ticket_rate" in d.rationale


def test_ship_when_significant_positive_and_no_negative_segment() -> None:
    assert decide(True, True, 0.03, OK_GUARDS, [POS, NULL]).decision == SHIP


def test_significant_overall_with_negative_segment_goes_segmented() -> None:
    d = decide(True, True, 0.03, OK_GUARDS, [POS, NEG])
    assert d.decision == SHIP_SEGMENTED
    assert d.positive_segments == [POS]
    assert "country=DE" in d.rationale


def test_not_significant_overall_but_positive_segment_goes_segmented() -> None:
    assert decide(True, False, 0.01, OK_GUARDS, [POS, NULL]).decision == SHIP_SEGMENTED


def test_significant_negative_overall_does_not_ship() -> None:
    assert decide(True, True, -0.03, OK_GUARDS, [NULL]).decision == DO_NOT_SHIP


def test_nothing_significant_does_not_ship() -> None:
    assert decide(True, False, 0.005, OK_GUARDS, [NULL]).decision == DO_NOT_SHIP


@pytest.mark.parametrize(
    "ci_low,threshold,expected", [(0.006, 0.005, True), (0.005, 0.005, False), (-0.01, 0.0, False)]
)
def test_breach_rule(ci_low: float, threshold: float, expected: bool) -> None:
    assert is_breached(ci_low, threshold) is expected


DF = pd.DataFrame(
    {
        "initial_decline_code": ["insufficient_funds"] * 4 + ["expired_card"] * 6,
        "country": ["US"] * 5 + ["DE"] * 5,
        "amount_usd": [10.0, 10.0, 20.0, 20.0] + [5.0] * 6,
    }
)


def test_impact_ship_all() -> None:
    r = revenue_impact(DF, SHIP, 0.03, [])
    assert r["ship_scope"] == "all"
    assert r["annualized_incremental_revenue_usd"] == pytest.approx(
        0.03 * 10 * 9.0 * 12
    )  # mean amount = 90 / 10


def test_impact_segmented_uses_one_dimension() -> None:
    us = seg("country", "US", 0.01, True)
    r = revenue_impact(DF, SHIP_SEGMENTED, 0.0, [POS, us])
    # insufficient_funds: 0.07 × 4 × 15 × 12 = 50.4 ; US: 0.01 × 5 × 12 × 12 = 7.2
    assert r["ship_scope"] == "segments"
    assert r["ship_segments"] == [
        {"dimension": "initial_decline_code", "value": "insufficient_funds"}
    ]
    assert r["annualized_incremental_revenue_usd"] == pytest.approx(50.4)
    assert len(r["assumptions"]) >= 5


def test_impact_do_not_ship_is_zero() -> None:
    r = revenue_impact(DF, DO_NOT_SHIP, 0.03, [])
    assert r["annualized_incremental_revenue_usd"] == 0.0
    assert r["ship_segments"] == []
