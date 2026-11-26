"""Annualized incremental revenue for the shipped scope."""

from __future__ import annotations

from typing import Any

import pandas as pd

from retrylab.analysis.decide import SHIP, SHIP_SEGMENTED

BASE_ASSUMPTIONS = [
    "Monthly failed-invoice volume equals the experiment window volume (both arms, one month).",
    "Incremental recovery per failed invoice equals the measured absolute lift in recovery rate.",
    "Each recovered invoice is worth the segment's average invoice amount (one month of "
    "subscription revenue); downstream retention value is excluded.",
    "Annualized as 12 × the monthly incremental revenue, with no seasonality or growth.",
    "The lift observed in the experiment persists after launch (no novelty decay).",
]


def _segment_impact(df: pd.DataFrame, seg: dict[str, Any]) -> float:
    rows = df[df[seg["dimension"]] == seg["value"]]
    return float(seg["abs_lift"]) * len(rows) * float(rows["amount_usd"].mean()) * 12.0


def revenue_impact(
    df: pd.DataFrame,
    decision: str,
    overall_abs_lift: float,
    positive_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Σ over shipped segments of (abs lift × monthly failed invoices × avg amount) × 12.

    * ``ship`` → one segment, the whole population, with the overall lift.
    * ``ship_segmented`` → segments from different dimensions overlap, so summing them would
      double count. We ship the significantly positive segments of the single dimension with
      the largest total impact (segments within one dimension are disjoint).
    * ``do_not_ship`` → nothing shipped, impact 0.
    """
    assumptions = list(BASE_ASSUMPTIONS)
    if decision == SHIP:
        value = overall_abs_lift * len(df) * float(df["amount_usd"].mean()) * 12.0
        assumptions.append("Shipped to all customers, using the overall (unadjusted) lift.")
        return {
            "annualized_incremental_revenue_usd": value,
            "ship_scope": "all",
            "ship_segments": [],
            "assumptions": assumptions,
        }
    if decision == SHIP_SEGMENTED and positive_segments:
        by_dim: dict[str, list[dict[str, Any]]] = {}
        for seg in positive_segments:
            by_dim.setdefault(seg["dimension"], []).append(seg)
        totals = {d: sum(_segment_impact(df, s) for s in segs) for d, segs in by_dim.items()}
        best = max(totals, key=lambda d: (totals[d], d))
        chosen = by_dim[best]
        assumptions.append(
            f"Shipped only to the BH-significant positive segments of '{best}', the dimension "
            "with the largest impact; segments of other dimensions overlap and are not added."
        )
        assumptions.append("Customers outside the shipped segments stay on the fixed schedule.")
        return {
            "annualized_incremental_revenue_usd": totals[best],
            "ship_scope": "segments",
            "ship_segments": [{"dimension": s["dimension"], "value": s["value"]} for s in chosen],
            "assumptions": assumptions,
        }
    assumptions.append("Nothing is shipped, so incremental revenue is zero.")
    return {
        "annualized_incremental_revenue_usd": 0.0,
        "ship_scope": "segments",
        "ship_segments": [],
        "assumptions": assumptions,
    }
