"""Segments: forest plot of segment lifts with Benjamini–Hochberg-adjusted significance."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app import data  # noqa: E402
from app.components import segment_label, setup_page, srm_alert, style_figure  # noqa: E402

setup_page("Segments")
st.caption(
    "Lift in recovery rate (treatment − control) per segment. Significance uses "
    "Benjamini–Hochberg-adjusted p-values across every segment row."
)

results = data.load_results()
if results is None:
    data.warn_missing("results")
    st.stop()

srm_alert(results)

segments = pd.DataFrame(results.get("segments") or [])
if segments.empty:
    st.info("results.json has no segment rows.")
    st.stop()

impact = results.get("revenue_impact") or {}
ship_segments = impact.get("ship_segments") or []
ship_keys = {(s.get("dimension"), s.get("value")) for s in ship_segments}
segments["recommended_to_ship"] = [
    (d, v) in ship_keys for d, v in zip(segments["dimension"], segments["value"], strict=True)
]

if impact.get("ship_scope") == "segments" and ship_segments:
    st.success(
        "**Recommended to ship:** "
        + ", ".join(segment_label(s["dimension"], s["value"]) for s in ship_segments)
    )
elif impact.get("ship_scope") == "all":
    st.info("The recommendation covers all customers, not specific segments.")

dims = [d for d in data.SEGMENT_DIMENSIONS if d in set(segments["dimension"])]
dims += sorted(set(segments["dimension"]) - set(dims))
choice = st.selectbox(
    "Segment dimension",
    ["All dimensions", *dims],
    format_func=lambda d: data.DIMENSION_LABELS.get(d, d),
)
view = segments if choice == "All dimensions" else segments[segments["dimension"] == choice]
view = view.sort_values(["dimension", "abs_lift"], ascending=[True, False]).reset_index(drop=True)

labels = [segment_label(d, v) for d, v in zip(view["dimension"], view["value"], strict=True)]
sig = view["significant_adj"].fillna(False).astype(bool)
fig = go.Figure()
for is_sig, name, color in (
    (True, "Significant after BH adjustment", data.COLORS["treatment"]),
    (False, "Not significant", data.COLORS["control"]),
):
    part = view[sig == is_sig]
    if part.empty:
        continue
    part_labels = [lab for lab, s in zip(labels, sig, strict=True) if s == is_sig]
    fig.add_trace(
        go.Scatter(
            x=part["abs_lift"] * 100,
            y=part_labels,
            mode="markers",
            name=name,
            marker={"size": 11, "color": color, "symbol": "circle" if is_sig else "circle-open"},
            error_x={
                "type": "data",
                "symmetric": False,
                "array": (part["ci_high"] - part["abs_lift"]) * 100,
                "arrayminus": (part["abs_lift"] - part["ci_low"]) * 100,
                "color": color,
            },
            customdata=part[["p_value", "p_value_adj"]].to_numpy(),
            hovertemplate=(
                "%{y}<br>lift %{x:+.2f}pp<br>p = %{customdata[0]:.3g}, "
                "BH-adjusted p = %{customdata[1]:.3g}<extra></extra>"
            ),
        )
    )
fig.add_vline(x=0, line_dash="dash", line_color=data.COLORS["control"])
fig.update_xaxes(title="Lift in recovery rate (percentage points, 95% CI)")
fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(labels)))
st.plotly_chart(style_figure(fig, height=max(300, 34 * len(view) + 120)))

st.subheader("Segment table")
st.caption("Click a column header to sort.")
table = view.rename(
    columns={
        "dimension": "Dimension",
        "value": "Segment",
        "n_control": "n control",
        "n_treatment": "n treatment",
        "control_rate": "Control rate",
        "treatment_rate": "Treatment rate",
        "abs_lift": "Lift",
        "ci_low": "CI low",
        "ci_high": "CI high",
        "p_value": "p",
        "p_value_adj": "BH-adjusted p",
        "significant_adj": "Significant (BH)",
        "recommended_to_ship": "Ship",
    }
)
pct_cols = ["Control rate", "Treatment rate", "Lift", "CI low", "CI high"]
for col in pct_cols:
    if col in table:
        table[col] = table[col] * 100
st.dataframe(
    table,
    hide_index=True,
    column_config={
        **{c: st.column_config.NumberColumn(c, format="%.1f%%") for c in pct_cols[:2]},
        **{c: st.column_config.NumberColumn(c, format="%+.2f pp") for c in pct_cols[2:]},
        "p": st.column_config.NumberColumn("p", format="%.4f"),
        "BH-adjusted p": st.column_config.NumberColumn("BH-adjusted p", format="%.4f"),
    },
)
