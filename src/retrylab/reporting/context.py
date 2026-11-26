"""Build the memo's template context from ``results.json`` (C6) and ``power_analysis.json`` (C5).

All numbers in the memo are formatted here from those two files; the template only arranges
them. Nothing here reads ``config/ground_truth.yaml`` (contract C7).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from retrylab.reporting import formatting as fmt
from retrylab.reporting.labels import (
    COUNT_METRICS,
    MONEY_METRICS,
    join_list,
    metric_label,
    segment_short,
    segment_subject,
)

DECISIONS = ("ship", "ship_segmented", "do_not_ship")

#: Figures the memo embeds when they exist, in display order, with captions.
FIGURES: tuple[tuple[str, str], ...] = (
    ("lift_overall.png", "Overall lift in recovery rate, raw and CUPED-adjusted, with 95% CIs"),
    ("segment_forest.png", "Lift by segment; BH-significant segments highlighted"),
    ("recovery_by_day.png", "Cumulative recovery over the 7-day retry window, by variant"),
    ("power_curve.png", "Minimum detectable effect vs. sample size per arm"),
)

#: An arm within this fraction of the planned size counts as hitting the plan.
PLAN_TOLERANCE = 0.98

#: How many significant segments to spell out before summarizing the rest.
MAX_SEGMENT_SENTENCES = 4


def load_json(path: str | Path) -> dict[str, Any]:
    """Read a JSON file into a dict."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Segment:
    """One results.json segment row, with pre-formatted strings."""

    dimension: str
    value: str
    subject: str
    short: str
    abs_lift: float
    lift: str
    control_rate: str
    treatment_rate: str
    ci: str
    p_adj: str
    p_adj_value: float
    n: str
    sentence: str = ""


@dataclass
class Guardrail:
    """One guardrail row, formatted."""

    metric: str
    label: str
    control: str
    treatment: str
    lift: str
    ci: str
    limit: str
    breached: bool


@dataclass
class Secondary:
    """One secondary metric row, formatted."""

    metric: str
    label: str
    control: str
    treatment: str
    lift: str
    ci: str
    p: str


@dataclass
class Figure:
    """An embedded figure: a path relative to the memo, and a caption."""

    path: str
    caption: str


@dataclass
class MemoContext:
    """Everything the template needs."""

    decision: str
    reason: str
    tldr: str
    rationale: str
    experiment_id: str
    generated_at: str
    n_control: str
    n_treatment: str
    n_total: str
    # design
    baseline_rate: str
    mde: str
    alpha: str
    power: str
    required_n: str
    planned_n: str
    achieved_power: str
    sample_vs_plan: str
    # primary
    primary_label: str
    control_rate: str
    treatment_rate: str
    abs_lift: str
    rel_lift: str
    ci: str
    ci_level: str
    p: str
    significant: bool
    cuped_covariate: str
    cuped_lift: str
    cuped_ci: str
    cuped_vr: str
    cuped_tighter: bool
    cuped_agrees: bool
    srm_passed: bool
    srm_p: str
    srm_threshold: str
    # sections
    secondary: list[Secondary] = field(default_factory=list)
    positive_segments: list[Segment] = field(default_factory=list)
    negative_segments: list[Segment] = field(default_factory=list)
    extra_positive_count: int = 0
    n_positive_segments: int = 0
    n_segments: int = 0
    n_null_segments: int = 0
    null_highlights: str = ""
    expired_card_null: bool = False
    guardrails: list[Guardrail] = field(default_factory=list)
    guardrails_held: bool = True
    breached_labels: str = ""
    ship_scope_text: str = ""
    ship_segments_text: str = ""
    annual_impact: str = ""
    rollout_steps: list[str] = field(default_factory=list)
    next_tests: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)


def _segment(row: dict[str, Any]) -> Segment:
    dim, val = row["dimension"], row["value"]
    seg = Segment(
        dimension=dim,
        value=val,
        subject=segment_subject(dim, val),
        short=segment_short(dim, val),
        abs_lift=float(row["abs_lift"]),
        lift=fmt.pp(abs(row["abs_lift"])),
        control_rate=fmt.pct(row["control_rate"]),
        treatment_rate=fmt.pct(row["treatment_rate"]),
        ci=fmt.ci_pp(row["ci_low"], row["ci_high"]),
        p_adj=fmt.pvalue(row["p_value_adj"]).replace("p ", "adjusted p ", 1),
        p_adj_value=float(row["p_value_adj"]),
        n=fmt.count(int(row["n_control"]) + int(row["n_treatment"])),
    )
    direction = "more" if seg.abs_lift >= 0 else "less"
    seg.sentence = (
        f"{seg.subject} recovered {seg.lift} {direction} often with smart retries "
        f"({seg.control_rate} → {seg.treatment_rate}, 95% CI {seg.ci}, {seg.p_adj}; "
        f"n = {seg.n})."
    )
    return seg


def _guardrail(row: dict[str, Any]) -> Guardrail:
    threshold = float(row["threshold_abs"])
    limit = "no increase allowed" if threshold == 0 else f"limit {fmt.signed_pp(threshold)}"
    return Guardrail(
        metric=row["metric"],
        label=metric_label(row["metric"]),
        control=fmt.pct(row["control"], 2),
        treatment=fmt.pct(row["treatment"], 2),
        lift=fmt.signed_pp(row["abs_lift"], 2),
        ci=fmt.ci_pp(row["ci_low"], row["ci_high"], 2),
        limit=limit,
        breached=bool(row["breached"]),
    )


def _secondary(row: dict[str, Any]) -> Secondary:
    metric = row["metric"]
    if metric in MONEY_METRICS:
        c, t = fmt.money(row["control"]), fmt.money(row["treatment"])
        lift = fmt.signed_money(row["abs_lift"])
        ci = fmt.ci_money(row["ci_low"], row["ci_high"])
    elif metric in COUNT_METRICS:
        c, t = f"{row['control']:.2f}", f"{row['treatment']:.2f}"
        lift = f"{row['abs_lift']:+.2f}"
        ci = f"[{row['ci_low']:.2f}, {row['ci_high']:.2f}]"
    else:
        c, t = fmt.pct(row["control"]), fmt.pct(row["treatment"])
        lift = fmt.signed_pp(row["abs_lift"])
        ci = fmt.ci_pp(row["ci_low"], row["ci_high"])
    return Secondary(
        metric=metric,
        label=metric_label(metric),
        control=c,
        treatment=t,
        lift=lift,
        ci=ci,
        p=fmt.pvalue(row["p_value"]),
    )


def _reason(results: dict[str, Any]) -> str:
    """Why the decision came out the way it did: srm | guardrail | no_effect | effect."""
    decision = results["recommendation"]["decision"]
    if decision != "do_not_ship":
        return "effect"
    if not results["srm"]["passed"]:
        return "srm"
    if any(g["breached"] for g in results.get("guardrails", [])):
        return "guardrail"
    return "no_effect"


def _figures(figures_dir: Path | None, memo_dir: Path | None) -> list[Figure]:
    if figures_dir is None or not figures_dir.is_dir():
        return []
    out: list[Figure] = []
    for name, caption in FIGURES:
        p = figures_dir / name
        if p.is_file():
            rel = os.path.relpath(p, memo_dir) if memo_dir is not None else str(p)
            out.append(Figure(path=Path(rel).as_posix(), caption=caption))
    return out


def build_context(
    results: dict[str, Any],
    power: dict[str, Any],
    figures_dir: Path | None = None,
    memo_dir: Path | None = None,
) -> MemoContext:
    """Turn the two report files into a fully formatted :class:`MemoContext`."""
    decision = results["recommendation"]["decision"]
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision {decision!r}; expected one of {DECISIONS}")
    reason = _reason(results)
    prim = results["primary"]
    cuped = results["cuped"]
    srm = results["srm"]
    impact = results["revenue_impact"]
    n_c, n_t = int(results["n_control"]), int(results["n_treatment"])
    planned = int(power["planned_n_per_arm"])

    # Segments
    segs = [_segment(r) for r in results.get("segments", [])]
    sig = [
        s for r, s in zip(results.get("segments", []), segs, strict=True) if r["significant_adj"]
    ]
    # Strongest evidence first (smallest adjusted p), so small noisy segments don't lead.
    pos = sorted((s for s in sig if s.abs_lift > 0), key=lambda s: (s.p_adj_value, -s.abs_lift))
    neg = sorted((s for s in sig if s.abs_lift < 0), key=lambda s: s.abs_lift)
    null = [s for s in segs if s not in sig]
    # Call out decline-code segments that showed nothing: they explain where the effect is not.
    null_decline = [s.short for s in null if s.dimension == "initial_decline_code"]

    # Shipped scope
    ship_keys = {(d["dimension"], d["value"]) for d in impact.get("ship_segments", [])}
    shipped = [s for s in segs if (s.dimension, s.value) in ship_keys]
    shipped_names = [s.short for s in shipped] or [
        segment_short(d["dimension"], d["value"]) for d in impact.get("ship_segments", [])
    ]
    ship_segments_text = join_list(shipped_names)
    if decision == "ship":
        ship_scope_text = "all customers with a failed subscription payment"
    elif decision == "ship_segmented":
        ship_scope_text = ship_segments_text or "the significantly positive segments"
    else:
        ship_scope_text = ""

    guardrails = [_guardrail(g) for g in results.get("guardrails", [])]
    breached = [g.label for g in guardrails if g.breached]

    annual = fmt.money(float(impact["annualized_incremental_revenue_usd"]))
    lift_phrase = (
        f"{fmt.signed_pp(prim['abs_lift'])} (95% CI {fmt.ci_pp(prim['ci_low'], prim['ci_high'])})"
    )
    rates_phrase = f"from {fmt.pct(prim['control'])} to {fmt.pct(prim['treatment'])}"

    if decision == "ship":
        tldr = (
            f"We recommend shipping smart retry timing to all customers. It raised the payment "
            f"recovery rate {rates_phrase}, {lift_phrase}, worth an estimated {annual} a year in "
            f"recovered revenue, with no guardrail breached."
        )
    elif decision == "ship_segmented":
        tldr = (
            f"We recommend shipping smart retry timing only for {ship_scope_text}, where the lift "
            f"is clear. Overall recovery moved {rates_phrase}, {lift_phrase}, and the targeted "
            f"rollout is worth an estimated {annual} a year."
        )
    elif reason == "srm":
        tldr = (
            f"We should not act on this test yet: the traffic split failed the sample-ratio check "
            f"({fmt.pvalue(srm['p_value'])}), so the measured lift of {lift_phrase} cannot be "
            f"trusted. We recommend fixing assignment and re-running."
        )
    elif reason == "guardrail":
        tldr = (
            f"We recommend not shipping smart retry timing. Recovery moved {rates_phrase}, "
            f"{lift_phrase}, but {join_list(breached)} rose past the agreed limit."
        )
    else:
        tldr = (
            f"We recommend not shipping smart retry timing. Recovery moved {rates_phrase}, "
            f"{lift_phrase}, which is not a reliable improvement, and no segment stood out."
        )

    if decision == "ship":
        rollout = [
            "Ramp smart retries to 10% of failed invoices for one week and confirm recovery and "
            "guardrails match the test.",
            "Expand to 50% for a second week, re-checking billing tickets and involuntary churn.",
            "Go to 100%, keeping a 5% holdout for a quarter to measure the long-run effect.",
        ]
        next_tests = [
            "Tune the smart policy for the segments with the smallest lift.",
            "Test a fifth retry or a longer window for high-value plans.",
        ]
    elif decision == "ship_segmented":
        rollout = [
            f"Turn on smart retries for {ship_scope_text} at 10%, then 50%, then 100% over three "
            "weeks, checking guardrails at each step.",
            "Keep the fixed schedule everywhere else, with a 5% holdout in the shipped segments.",
        ]
        next_tests = [
            "Design a different treatment for segments with no lift (e.g., card-updater "
            "prompts for expired cards instead of better timing).",
            "Re-test the remaining segments with a larger sample if a smaller effect matters.",
        ]
    elif reason == "srm":
        rollout = ["No rollout. Audit the assignment and logging pipeline for dropped customers."]
        next_tests = ["Re-run the experiment once the split is verified with an A/A test."]
    elif reason == "guardrail":
        rollout = ["No rollout. Keep the fixed retry schedule."]
        next_tests = [
            "Find what drove the guardrail regression (e.g., retry hour or retry count) and test "
            "a gentler variant with the same guardrails.",
        ]
    else:
        rollout = ["No rollout. Keep the fixed retry schedule."]
        next_tests = [
            "Test a bigger change, such as account-updater integration or customer outreach "
            "before the retry.",
        ]

    achieved = min(n_c, n_t)
    if achieved >= PLAN_TOLERANCE * planned:
        sample_vs_plan = "hit that plan"
    elif achieved >= int(power["required_n_per_arm"]):
        sample_vs_plan = "fell short of it but cleared the required sample"
    else:
        sample_vs_plan = "fell short of the required sample, so the test is underpowered"
    cuped_tighter = (cuped["ci_high"] - cuped["ci_low"]) < (prim["ci_high"] - prim["ci_low"])
    # CUPED only "confirms" a significant raw lift if its CI excludes zero on the same side.
    cuped_agrees = cuped["ci_low"] > 0 if prim["abs_lift"] >= 0 else cuped["ci_high"] < 0

    return MemoContext(
        decision=decision,
        reason=reason,
        tldr=tldr,
        rationale=results["recommendation"]["rationale"],
        experiment_id=results["experiment_id"],
        generated_at=results["generated_at"],
        n_control=fmt.count(n_c),
        n_treatment=fmt.count(n_t),
        n_total=fmt.count(n_c + n_t),
        baseline_rate=fmt.pct(power["baseline_rate"]),
        mde=fmt.pp(power["mde_abs"]),
        alpha=f"{power['alpha']:g}",
        power=fmt.pct(power["power"], 0),
        required_n=fmt.count(power["required_n_per_arm"]),
        planned_n=fmt.count(planned),
        achieved_power=fmt.pct(power["achieved_power_at_mde"]),
        sample_vs_plan=sample_vs_plan,
        primary_label=metric_label(prim["metric"]),
        control_rate=fmt.pct(prim["control"]),
        treatment_rate=fmt.pct(prim["treatment"]),
        abs_lift=fmt.signed_pp(prim["abs_lift"]),
        rel_lift=f"{prim['rel_lift'] * 100:+.1f}%",
        ci=fmt.ci_pp(prim["ci_low"], prim["ci_high"]),
        ci_level=fmt.pct(prim["ci_level"], 0),
        p=fmt.pvalue(prim["p_value"]),
        significant=bool(prim["significant"]),
        cuped_covariate=cuped["covariate"],
        cuped_lift=fmt.signed_pp(cuped["abs_lift"]),
        cuped_ci=fmt.ci_pp(cuped["ci_low"], cuped["ci_high"]),
        cuped_vr=fmt.plain_pct(cuped["variance_reduction_pct"]),
        cuped_tighter=cuped_tighter,
        cuped_agrees=cuped_agrees,
        srm_passed=bool(srm["passed"]),
        srm_p=fmt.pvalue(srm["p_value"]),
        srm_threshold=f"{srm['threshold']:g}",
        secondary=[_secondary(r) for r in results.get("secondary", [])],
        positive_segments=pos[:MAX_SEGMENT_SENTENCES],
        negative_segments=neg,
        extra_positive_count=max(0, len(pos) - MAX_SEGMENT_SENTENCES),
        n_positive_segments=len(pos),
        n_segments=len(segs),
        n_null_segments=len(null),
        null_highlights=join_list(null_decline),
        expired_card_null=any(
            s.dimension == "initial_decline_code" and s.value == "expired_card" for s in null
        ),
        guardrails=guardrails,
        guardrails_held=not breached,
        breached_labels=join_list(breached),
        ship_scope_text=ship_scope_text,
        ship_segments_text=ship_segments_text,
        annual_impact=annual,
        rollout_steps=rollout,
        next_tests=next_tests,
        assumptions=list(impact.get("assumptions", [])),
        figures=_figures(figures_dir, memo_dir),
    )
