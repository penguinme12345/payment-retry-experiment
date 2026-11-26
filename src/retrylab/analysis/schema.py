"""Pydantic model mirroring contract C6 (``reports/results.json``)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Srm(_Strict):
    chi2: float
    p_value: float
    passed: bool
    threshold: float


class Primary(_Strict):
    metric: str
    control: float
    treatment: float
    abs_lift: float
    rel_lift: float
    ci_low: float
    ci_high: float
    ci_level: float
    p_value: float
    significant: bool


class Cuped(_Strict):
    covariate: str
    abs_lift: float
    ci_low: float
    ci_high: float
    variance_reduction_pct: float


class Secondary(_Strict):
    metric: str
    control: float
    treatment: float
    abs_lift: float
    ci_low: float
    ci_high: float
    p_value: float


class Guardrail(_Strict):
    metric: str
    control: float
    treatment: float
    abs_lift: float
    ci_low: float
    ci_high: float
    p_value: float
    threshold_abs: float
    breached: bool


class Segment(_Strict):
    dimension: str
    value: str
    n_control: int
    n_treatment: int
    control_rate: float
    treatment_rate: float
    abs_lift: float
    ci_low: float
    ci_high: float
    p_value: float
    p_value_adj: float
    significant_adj: bool


class SegmentRef(_Strict):
    dimension: str
    value: str


class RevenueImpact(_Strict):
    annualized_incremental_revenue_usd: float
    ship_scope: Literal["all", "segments"]
    ship_segments: list[SegmentRef]
    assumptions: list[str]


class Recommendation(_Strict):
    decision: Literal["ship", "ship_segmented", "do_not_ship"]
    rationale: str


class Results(_Strict):
    experiment_id: str
    generated_at: str
    n_control: int
    n_treatment: int
    srm: Srm
    primary: Primary
    cuped: Cuped
    secondary: list[Secondary]
    guardrails: list[Guardrail]
    segments: list[Segment]
    revenue_impact: RevenueImpact
    recommendation: Recommendation
