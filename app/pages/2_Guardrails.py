"""Guardrails: customer-harm metrics with their thresholds and breach status."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app import data  # noqa: E402
from app.components import pp, setup_page, srm_alert, style_figure  # noqa: E402

GUARDRAIL_LABELS = {
    "billing_ticket_rate": "Billing ticket rate (14 days)",
    "involuntary_churn_rate": "Involuntary churn rate (30 days)",
}

setup_page("Guardrails")
st.caption(
    "Smart retries must not hurt customers. A guardrail is breached when its lift exceeds the "
    "maximum acceptable increase set in the experiment design."
)

results = data.load_results()
if results is None:
    data.warn_missing("results")
else:
    srm_alert(results)
    guardrails = pd.DataFrame(results.get("guardrails") or [])
    if guardrails.empty:
        st.info("results.json has no guardrail rows.")
    else:
        breached = guardrails[guardrails["breached"].fillna(False).astype(bool)]
        if breached.empty:
            st.success(f"All {len(guardrails)} guardrails held.")
        else:
            st.error(
                "**Guardrail breached:** "
                + ", ".join(GUARDRAIL_LABELS.get(m, m) for m in breached["metric"])
            )
        table = pd.DataFrame(
            {
                "Guardrail": [GUARDRAIL_LABELS.get(m, m) for m in guardrails["metric"]],
                "Control": guardrails["control"] * 100,
                "Treatment": guardrails["treatment"] * 100,
                "Lift": guardrails["abs_lift"] * 100,
                "CI low": guardrails["ci_low"] * 100,
                "CI high": guardrails["ci_high"] * 100,
                "p": guardrails["p_value"],
                "Max increase": guardrails["threshold_abs"] * 100,
                "Status": ["BREACHED" if b else "OK" for b in guardrails["breached"]],
            }
        )
        st.dataframe(
            table,
            hide_index=True,
            column_config={
                "Control": st.column_config.NumberColumn(format="%.2f%%"),
                "Treatment": st.column_config.NumberColumn(format="%.2f%%"),
                "Lift": st.column_config.NumberColumn(format="%+.2f pp"),
                "CI low": st.column_config.NumberColumn(format="%+.2f pp"),
                "CI high": st.column_config.NumberColumn(format="%+.2f pp"),
                "p": st.column_config.NumberColumn(format="%.4f"),
                "Max increase": st.column_config.NumberColumn(format="%.2f pp"),
            },
        )
        for _, g in guardrails.iterrows():
            st.caption(
                f"{GUARDRAIL_LABELS.get(g['metric'], g['metric'])}: lift {pp(g['abs_lift'], 2)} "
                f"(95% CI {pp(g['ci_low'], 2)} to {pp(g['ci_high'], 2)}) vs. a maximum of "
                f"{pp(g['threshold_abs'], 2, sign=False)}."
            )

st.subheader("Billing ticket and churn rates by variant")
summary = data.load_summary()
source = "warehouse mart `agg_experiment_summary`"
if summary is None:
    if not data.warehouse_available():
        data.warn_missing("warehouse")
    else:
        st.warning("The warehouse has no `agg_experiment_summary` table. Run `make dbt`.")
    if results and results.get("guardrails"):
        source = "`results.json`"
        rows = []
        for g in results["guardrails"]:
            for v in data.VARIANTS:
                rows.append({"variant": v, "metric": g["metric"], "rate": g[v]})
        rates = pd.DataFrame(rows)
    else:
        rates = None
else:
    rates = summary.melt(
        id_vars="variant",
        value_vars=[c for c in GUARDRAIL_LABELS if c in summary.columns],
        var_name="metric",
        value_name="rate",
    )

if rates is not None and not rates.empty:
    fig = go.Figure()
    for v in data.VARIANTS:
        part = rates[rates["variant"] == v]
        fig.add_trace(
            go.Bar(
                x=[GUARDRAIL_LABELS.get(m, m) for m in part["metric"]],
                y=part["rate"] * 100,
                name=v,
                marker_color=data.COLORS[v],
                text=[f"{r * 100:.2f}%" for r in part["rate"]],
                textposition="outside",
            )
        )
    fig.update_layout(barmode="group")
    fig.update_yaxes(title="Rate (%)")
    st.plotly_chart(style_figure(fig))
    st.caption(f"Source: {source}.")
