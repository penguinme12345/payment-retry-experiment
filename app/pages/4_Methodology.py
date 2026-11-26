"""Methodology: power analysis summary and the experiment design document."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app import data  # noqa: E402
from app.components import pct, pp, setup_page, style_figure  # noqa: E402

DESIGN_DOC_URL = (
    "https://github.com/penguinme12345/payment-retry-experiment/blob/main/docs/experiment_design.md"
)

setup_page("Methodology")
st.markdown(
    "Customers with one failed invoice in March 2026 were randomized 50/50 at the customer level. "
    "Control retries at +1, +3, +5 and +7 days; treatment uses the same budget of up to 4 retries "
    "within 7 days, timed around the customer's payday and historical success hour. The primary "
    "metric is the 7-day recovery rate; guardrails are 14-day billing tickets and 30-day "
    "involuntary churn. Inference (CIs, p-values, CUPED, Benjamini–Hochberg) is computed upstream "
    "in `reports/results.json`; this dashboard only displays it."
)

power = data.load_power()
if power is None:
    data.warn_missing("power")
else:
    st.subheader("Power analysis")
    cols = st.columns(5)
    cols[0].metric("Baseline recovery rate", pct(power.get("baseline_rate")))
    cols[1].metric("Minimum detectable effect", pp(power.get("mde_abs"), sign=False))
    cols[2].metric(
        "Required n per arm",
        f"{power.get('required_n_per_arm', 0):,}",
        help=f"alpha {power.get('alpha')}, power {power.get('power')}, "
        + ("two-sided" if power.get("two_sided", True) else "one-sided"),
    )
    cols[3].metric("Planned n per arm", f"{power.get('planned_n_per_arm', 0):,}")
    cols[4].metric("Power at the MDE", pct(power.get("achieved_power_at_mde")))

    curve = pd.DataFrame(power.get("mde_curve") or [])
    if not curve.empty:
        fig = go.Figure(
            go.Scatter(
                x=curve["n_per_arm"],
                y=curve["mde_abs"] * 100,
                mode="lines+markers",
                line={"color": data.COLORS["treatment"]},
                name="MDE",
                hovertemplate="n = %{x:,}: MDE %{y:.2f}pp<extra></extra>",
            )
        )
        if power.get("planned_n_per_arm"):
            fig.add_vline(
                x=power["planned_n_per_arm"],
                line_dash="dash",
                line_color=data.COLORS["control"],
                annotation_text="planned",
            )
        if power.get("required_n_per_arm"):
            fig.add_vline(
                x=power["required_n_per_arm"],
                line_dash="dot",
                line_color=data.COLORS["control"],
                annotation_text="required",
            )
        fig.update_xaxes(title="Customers per arm")
        fig.update_yaxes(title="Minimum detectable effect (pp)", rangemode="tozero")
        st.markdown("**Power curve:** the smallest lift detectable at each sample size")
        st.plotly_chart(style_figure(fig, height=340))

    guardrails = power.get("guardrails") or []
    if guardrails:
        st.markdown("**Guardrail thresholds**")
        st.dataframe(
            pd.DataFrame(
                {
                    "Metric": [g.get("metric") for g in guardrails],
                    "Max acceptable increase": [
                        pp(g.get("max_acceptable_increase_abs"), 2, sign=False) for g in guardrails
                    ],
                }
            ),
            hide_index=True,
        )

st.subheader("Experiment design")
st.markdown(
    f"Full design: [`docs/experiment_design.md`]({DESIGN_DOC_URL}) "
    f"(local copy: `{data.input_path('design_doc')}`)."
)
doc = data.load_design_doc()
if doc is None:
    data.warn_missing("design_doc")
else:
    with st.expander("Read the design document here"):
        st.markdown(doc)
