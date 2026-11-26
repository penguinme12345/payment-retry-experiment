"""RetryLab dashboard: Overview page. Launch with ``streamlit run app/Home.py``."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app import data  # noqa: E402
from app.components import (  # noqa: E402
    SECONDARY_LABELS,
    decision_banner,
    pct,
    pp,
    setup_page,
    srm_alert,
    style_figure,
    usd_rounded,
)

setup_page("Smart retry timing experiment")
st.caption(
    f"Experiment `{data.EXPERIMENT_ID}`: smart, payday-aware retry timing (treatment) vs. a fixed "
    "+1/+3/+5/+7 day schedule (control) for failed subscription payments, March 2026."
)

results = data.load_results()
if results is None:
    data.warn_missing("results")
    st.stop()

srm_alert(results)
decision_banner(results)

primary = results.get("primary") or {}
cuped = results.get("cuped") or {}
srm = results.get("srm") or {}
impact = results.get("revenue_impact") or {}

st.subheader("Key numbers")
cols = st.columns(5)
n_control, n_treatment = results.get("n_control"), results.get("n_treatment")
cols[0].metric("Recovery rate, control", pct(primary.get("control")))
cols[0].caption(f"n = {n_control:,}" if isinstance(n_control, int) else "")
cols[1].metric(
    "Recovery rate, treatment",
    pct(primary.get("treatment")),
    delta=pp(primary.get("abs_lift")),
)
cols[1].caption(f"n = {n_treatment:,}" if isinstance(n_treatment, int) else "")
cols[2].metric(
    "Absolute lift",
    pp(primary.get("abs_lift")),
    help=(
        f"Relative lift {pct(primary.get('rel_lift'))}, "
        f"p = {primary.get('p_value', float('nan')):.2g}"
    ),
)
cols[2].caption(
    f"{int(primary.get('ci_level', 0.95) * 100)}% CI {pp(primary.get('ci_low'))} to "
    f"{pp(primary.get('ci_high'))}, "
    + ("significant" if primary.get("significant") else "not significant")
)
cols[3].metric(
    "Annualized revenue impact",
    usd_rounded(impact.get("annualized_incremental_revenue_usd")),
)
cols[3].caption(
    "if shipped to all customers"
    if impact.get("ship_scope") == "all"
    else "if shipped to the recommended segments"
)
cols[4].metric("Sample ratio check", "Passed" if srm.get("passed", False) else "FAILED")
cols[4].caption(f"chi² p = {srm.get('p_value', float('nan')):.3g}")

st.subheader("Lift in recovery rate, with confidence interval")
rows = [
    {
        "estimate": "Raw difference",
        "abs_lift": primary.get("abs_lift"),
        "ci_low": primary.get("ci_low"),
        "ci_high": primary.get("ci_high"),
    }
]
if cuped:
    rows.append(
        {
            "estimate": f"CUPED ({cuped.get('covariate', 'covariate')})",
            "abs_lift": cuped.get("abs_lift"),
            "ci_low": cuped.get("ci_low"),
            "ci_high": cuped.get("ci_high"),
        }
    )
lift = pd.DataFrame(rows).dropna()
if lift.empty:
    st.info("results.json has no lift estimates to plot.")
else:
    lift[["abs_lift", "ci_low", "ci_high"]] *= 100
    fig = go.Figure(
        go.Scatter(
            x=lift["abs_lift"],
            y=lift["estimate"],
            mode="markers+text",
            text=[f"{v:+.2f}pp" for v in lift["abs_lift"]],
            textposition="top center",
            cliponaxis=False,
            marker={"size": 14, "color": data.COLORS["treatment"]},
            error_x={
                "type": "data",
                "symmetric": False,
                "array": lift["ci_high"] - lift["abs_lift"],
                "arrayminus": lift["abs_lift"] - lift["ci_low"],
                "color": data.COLORS["treatment"],
                "thickness": 2,
                "width": 8,
            },
            hovertemplate="%{y}: %{x:+.2f}pp<extra></extra>",
            showlegend=False,
        )
    )
    fig.add_vline(x=0, line_dash="dash", line_color=data.COLORS["control"])
    fig.update_xaxes(title="Treatment − control recovery rate (percentage points)", zeroline=False)
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(style_figure(fig, height=280))
    if cuped.get("variance_reduction_pct") is not None:
        st.caption(
            f"CUPED on `{cuped.get('covariate')}` cut variance by "
            f"{cuped['variance_reduction_pct']:.1f}%, which narrows the interval."
        )

secondary = results.get("secondary") or []
if secondary:
    st.subheader("Secondary metrics")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Metric": SECONDARY_LABELS.get(r["metric"], r["metric"]),
                    "Control": r["control"],
                    "Treatment": r["treatment"],
                    "Difference": r["abs_lift"],
                    "95% CI": f"[{r['ci_low']:.2f}, {r['ci_high']:.2f}]",
                    "p-value": "< 0.001" if r["p_value"] < 0.001 else f"{r['p_value']:.3f}",
                }
                for r in secondary
            ]
        ),
        hide_index=True,
        column_config={
            c: st.column_config.NumberColumn(format="%.2f")
            for c in ("Control", "Treatment", "Difference")
        },
    )

assumptions = impact.get("assumptions") or []
if assumptions:
    with st.expander("Revenue impact assumptions"):
        for a in assumptions:
            st.markdown(f"- {a}")

st.caption(
    f"Results generated {results.get('generated_at', 'n/a')}. Use the sidebar for more pages."
)
