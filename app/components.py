"""Shared UI pieces for the RetryLab dashboard pages."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import streamlit as st

from app.data import COLORS, DIMENSION_LABELS

DECISION_TEXT: dict[str, tuple[str, str]] = {
    "ship": ("success", "Decision: SHIP smart retries to all customers"),
    "ship_segmented": (
        "info",
        "Decision: SHIP SEGMENTED (smart retries for selected segments only)",
    ),
    "do_not_ship": ("error", "Decision: DON'T SHIP (keep the fixed retry schedule)"),
}


def setup_page(title: str, icon: str = "🔁") -> None:
    """Configure the page and print its header."""
    st.set_page_config(page_title=f"RetryLab · {title}", page_icon=icon, layout="wide")
    st.title(title)


def decision_text(decision: str | None) -> str:
    """Human-readable banner text for a ``recommendation.decision`` value."""
    if decision in DECISION_TEXT:
        return DECISION_TEXT[decision][1]
    return f"Decision: unrecognised value `{decision}`"


def decision_banner(results: dict[str, Any]) -> None:
    """Show the ship / ship segmented / don't ship banner with its rationale."""
    rec = results.get("recommendation") or {}
    decision = rec.get("decision")
    rationale = rec.get("rationale") or ""
    kind = DECISION_TEXT.get(decision, ("warning", ""))[0]
    body = f"**{decision_text(decision)}**"
    if rationale:
        body += f"\n\n{rationale}"
    getattr(st, kind)(body)


def srm_alert(results: dict[str, Any]) -> None:
    """Loud warning when the sample-ratio-mismatch check failed."""
    srm = results.get("srm") or {}
    if srm and not srm.get("passed", True):
        st.error(
            f"**Sample ratio mismatch detected** (p = {srm.get('p_value', float('nan')):.2g}, "
            f"threshold {srm.get('threshold', 0.001)}). The randomization may be broken, so treat "
            "every result on this dashboard as untrustworthy until it is explained."
        )


def pct(x: Any, digits: int = 1) -> str:
    """Format a rate as a percentage."""
    try:
        return f"{float(x) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "n/a"


def pp(x: Any, digits: int = 1, sign: bool = True) -> str:
    """Format an absolute difference in rates as percentage points."""
    try:
        v = float(x) * 100
    except (TypeError, ValueError):
        return "n/a"
    return f"{v:+.{digits}f}pp" if sign else f"{v:.{digits}f}pp"


def usd(x: Any, digits: int = 0) -> str:
    """Format a USD amount."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    return f"-${abs(v):,.{digits}f}" if v < 0 else f"${v:,.{digits}f}"


def usd_rounded(x: Any) -> str:
    """USD rounded the way the memo and README round it: nearest $100 at $1,000 and above."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    if abs(v) >= 1_000:
        v = round(v, -2)
    return usd(v)


SECONDARY_LABELS = {
    "recovered_revenue_per_invoice_usd": "Recovered revenue per failed invoice ($)",
    "avg_retries_per_invoice": "Retries per failed invoice",
    "hours_to_recovery": "Hours to recovery (recovered invoices)",
}


def segment_label(dimension: str, value: str) -> str:
    """``Decline code: insufficient_funds`` style label."""
    return f"{DIMENSION_LABELS.get(dimension, dimension)}: {value}"


def style_figure(fig: go.Figure, height: int = 380) -> go.Figure:
    """Consistent, quiet chart styling."""
    fig.update_layout(
        height=height,
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


__all__ = [
    "COLORS",
    "decision_banner",
    "decision_text",
    "pct",
    "pp",
    "segment_label",
    "setup_page",
    "srm_alert",
    "style_figure",
    "usd",
]
