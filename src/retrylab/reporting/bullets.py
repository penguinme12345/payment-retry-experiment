"""Resume bullets from ``results.json``: ``python -m retrylab.reporting.bullets``.

Three bullets, each under 160 characters, with real numbers from the results file.
"""

from __future__ import annotations

import argparse
from typing import Any

from retrylab.reporting import formatting as fmt
from retrylab.reporting.context import load_json
from retrylab.reporting.labels import join_list, segment_short
from retrylab.reporting.paths import resolve

MAX_CHARS = 159


def _first_fit(candidates: list[str]) -> str:
    for c in candidates:
        if len(c) <= MAX_CHARS:
            return c
    return candidates[-1][:MAX_CHARS]


def make_bullets(results: dict[str, Any]) -> list[str]:
    """Return three resume bullets, longest-fitting phrasing first."""
    prim = results["primary"]
    n = fmt.count(int(results["n_control"]) + int(results["n_treatment"]))
    lift = fmt.signed_pp(prim["abs_lift"])
    ci = fmt.ci_pp(prim["ci_low"], prim["ci_high"])
    vr = fmt.plain_pct(results["cuped"]["variance_reduction_pct"])
    segs = results.get("segments", [])
    n_sig = sum(1 for s in segs if s["significant_adj"])
    impact = results["revenue_impact"]
    annual = fmt.money(float(impact["annualized_incremental_revenue_usd"]))
    decision = results["recommendation"]["decision"]

    b1 = _first_fit(
        [
            f"Designed and analyzed a {n}-customer A/B test of smart payment-retry timing; "
            f"recovery rate moved {lift} (95% CI {ci}, {fmt.pvalue(prim['p_value'])}).",
            f"Ran a {n}-customer A/B test of smart payment retries; recovery moved {lift} "
            f"(95% CI {ci}).",
        ]
    )
    b2 = _first_fit(
        [
            f"Built a dbt + DuckDB metrics layer and Python stats pipeline with CUPED "
            f"({vr} variance cut) and BH-corrected cuts: {n_sig} of {len(segs)} segments "
            f"significant.",
            f"Built dbt metrics + CUPED analysis ({vr} variance cut); {n_sig} of {len(segs)} "
            f"segments significant after BH correction.",
        ]
    )
    if decision == "ship":
        verdict = "a full launch"
    elif decision == "ship_segmented":
        names = [segment_short(d["dimension"], d["value"]) for d in impact["ship_segments"]]
        verdict = f"a targeted launch for {join_list(names)}"
    else:
        verdict = "not launching"
    b3 = _first_fit(
        [
            f"Wrote a decision memo and Streamlit dashboard recommending {verdict}, sized at "
            f"{annual}/yr in recovered revenue.",
            f"Wrote a decision memo and dashboard recommending {verdict} ({annual}/yr).",
            f"Wrote a launch memo and dashboard sizing {annual}/yr in recovered revenue.",
        ]
    )
    return [b1, b2, b3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m retrylab.reporting.bullets")
    parser.add_argument("--results", default="reports/results.json")
    args = parser.parse_args(argv)
    for b in make_bullets(load_json(resolve(args.results))):
        print(f"- {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
