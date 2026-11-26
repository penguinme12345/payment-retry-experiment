"""Pre-registered decision rules (PRD-C §7, as specified in PRD-D §3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SHIP = "ship"
SHIP_SEGMENTED = "ship_segmented"
DO_NOT_SHIP = "do_not_ship"


@dataclass(frozen=True)
class Decision:
    decision: str
    rationale: str
    #: Significantly positive segments (BH-adjusted); candidates for a segmented launch.
    positive_segments: list[dict[str, Any]] = field(default_factory=list)


def _label(seg: dict[str, Any]) -> str:
    return f"{seg['dimension']}={seg['value']}"


def decide(
    srm_passed: bool,
    primary_significant: bool,
    primary_abs_lift: float,
    guardrails: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> Decision:
    """Apply the rules in order; the first one that matches wins.

    1. SRM failed → ``do_not_ship`` (invalid experiment).
    2. Any guardrail breached → ``do_not_ship``.
    3. Overall lift significant and positive, and no segment significantly negative → ``ship``.
    4. Some segment significantly positive → ``ship_segmented``.
    5. Otherwise → ``do_not_ship``.
    """
    positive = [s for s in segments if s["significant_adj"] and s["abs_lift"] > 0]
    negative = [s for s in segments if s["significant_adj"] and s["abs_lift"] < 0]

    if not srm_passed:
        return Decision(
            DO_NOT_SHIP,
            "Do not ship: the sample ratio mismatch check failed, so this is an invalid "
            "experiment and its results cannot be trusted.",
        )
    breached = [g["metric"] for g in guardrails if g["breached"]]
    if breached:
        return Decision(
            DO_NOT_SHIP,
            f"Do not ship: the {', '.join(breached)} guardrail is confidently worse than the "
            "allowed increase.",
        )
    if primary_significant and primary_abs_lift > 0 and not negative:
        return Decision(
            SHIP,
            f"Ship to all customers: recovery rate rose by {primary_abs_lift * 100:.1f}pp "
            "(significant), no segment was significantly hurt, and no guardrail was breached.",
            positive,
        )
    if positive:
        if primary_significant and primary_abs_lift > 0:
            why = (
                f"the overall lift is significant but {', '.join(_label(s) for s in negative)} "
                "is significantly hurt"
            )
        elif primary_significant:
            why = "the overall effect is significantly negative"
        else:
            why = "the overall lift is not significant"
        return Decision(
            SHIP_SEGMENTED,
            f"Ship only to {', '.join(_label(s) for s in positive)}: {why}, while these "
            "segments improve significantly after BH correction.",
            positive,
        )
    return Decision(
        DO_NOT_SHIP,
        "Do not ship: neither the overall lift nor any segment's lift is significantly positive.",
    )
