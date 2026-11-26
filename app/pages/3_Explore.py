"""Explore: descriptive, filterable view of the experiment fact table."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app import data  # noqa: E402
from app.components import pct, pp, setup_page, style_figure, usd  # noqa: E402

DESCRIPTIVE_NOTE = "Descriptive only. See Segments for significance."

setup_page("Explore")
st.warning(DESCRIPTIVE_NOTE, icon="🔎")

if not data.warehouse_available():
    data.warn_missing("warehouse")
    st.stop()

options = data.load_filter_options()
if options is None:
    st.warning("The warehouse has no `fct_experiment_invoices` table. Run `make dbt`.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    filters = {
        dim: st.multiselect(data.DIMENSION_LABELS[dim], options[dim], key=f"filter_{dim}")
        for dim in data.SEGMENT_DIMENSIONS
    }
active = {k: v for k, v in filters.items() if v}
if active:
    st.caption(
        "Filtered to "
        + "; ".join(f"{data.DIMENSION_LABELS[k]} in {', '.join(v)}" for k, v in active.items())
    )
else:
    st.caption("No filters applied: showing every experiment invoice.")

rec = data.filtered_recovery(active)
if rec is None or rec.empty:
    st.info("No invoices match these filters.")
    st.stop()

by_variant = rec.set_index("variant")
cols = st.columns(4)
for i, v in enumerate(data.VARIANTS):
    if v in by_variant.index:
        row = by_variant.loc[v]
        cols[i].metric(
            f"Recovery rate, {v}", pct(row["recovery_rate"]), help=f"n = {int(row['n_invoices']):,}"
        )
if set(data.VARIANTS) <= set(by_variant.index):
    diff = by_variant.loc["treatment", "recovery_rate"] - by_variant.loc["control", "recovery_rate"]
    cols[2].metric("Difference (descriptive)", pp(diff))
cols[3].metric("Invoices", f"{int(rec['n_invoices'].sum()):,}")

table = rec.rename(
    columns={
        "variant": "Variant",
        "n_invoices": "Invoices",
        "n_recovered": "Recovered",
        "recovery_rate": "Recovery rate",
        "recovered_revenue_usd": "Recovered revenue",
        "recovered_revenue_per_invoice_usd": "Revenue per invoice",
        "avg_retries_per_invoice": "Avg retries",
    }
)
table["Recovery rate"] = table["Recovery rate"] * 100
st.dataframe(
    table,
    hide_index=True,
    column_config={
        "Recovery rate": st.column_config.NumberColumn(format="%.1f%%"),
        "Recovered revenue": st.column_config.NumberColumn(format="$%.0f"),
        "Revenue per invoice": st.column_config.NumberColumn(format="$%.2f"),
        "Avg retries": st.column_config.NumberColumn(format="%.2f"),
    },
)
st.caption(
    "Recovered revenue: "
    + ", ".join(f"{r.variant} {usd(r.recovered_revenue_usd)}" for r in rec.itertuples())
)

left, right = st.columns(2)

with left:
    st.subheader("Cumulative recovery by hour since failure")
    curve = data.filtered_recovery_curve(active)
    if curve is not None and not curve.empty:
        fig = go.Figure()
        for v in data.VARIANTS:
            part = curve[curve["variant"] == v]
            fig.add_trace(
                go.Scatter(
                    x=part["hour"],
                    y=part["cumulative_recovery_rate"] * 100,
                    mode="lines",
                    name=v,
                    line={"color": data.COLORS[v], "width": 2, "shape": "hv"},
                    hovertemplate="hour %{x}: %{y:.1f}%<extra>" + v + "</extra>",
                )
            )
        fig.update_xaxes(title="Hours since initial failure", dtick=24, range=[0, 168])
        fig.update_yaxes(title="Recovered so far (%)", rangemode="tozero")
        st.plotly_chart(style_figure(fig))

with right:
    st.subheader("Retries attempted per invoice")
    retries = data.filtered_retries(active)
    if retries is not None and not retries.empty:
        fig = go.Figure()
        for v in data.VARIANTS:
            part = retries[retries["variant"] == v]
            fig.add_trace(
                go.Bar(
                    x=part["retries_attempted"],
                    y=part["share"] * 100,
                    name=v,
                    marker_color=data.COLORS[v],
                    customdata=part["n_invoices"],
                    hovertemplate="%{x} retries: %{y:.1f}% (%{customdata:,} invoices)<extra>"
                    + v
                    + "</extra>",
                )
            )
        fig.update_layout(barmode="group")
        fig.update_xaxes(title="Retries attempted", dtick=1)
        fig.update_yaxes(title="Share of invoices in variant (%)")
        st.plotly_chart(style_figure(fig))

st.caption(DESCRIPTIVE_NOTE)
