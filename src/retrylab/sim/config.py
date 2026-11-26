"""Config loading for the simulator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DECLINE_CODES = ("insufficient_funds", "expired_card", "do_not_honor", "generic_decline")


@dataclass(frozen=True)
class GroundTruth:
    baseline_recovery: dict[str, float]
    treatment_lift_abs: dict[str, float]
    payday_known_extra_lift_abs: float
    billing_ticket_rate: dict[str, float]
    involuntary_churn_given_unrecovered: float
    voluntary_churn_30d: float


@dataclass(frozen=True)
class SimConfig:
    seed: int
    n_customers: int
    country_mix: dict[str, float]
    plan_mix: dict[str, float]
    funding_mix: dict[str, float]
    brand_mix: dict[str, float]
    decline_mix: dict[str, float]
    payday_known_rate: float
    pre_period_months: int
    inject_srm: bool
    truth: GroundTruth


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open() as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _check_mix(name: str, mix: dict[str, float]) -> dict[str, float]:
    total = sum(mix.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"{name} must sum to 1.0, got {total}")
    return {str(k): float(v) for k, v in mix.items()}


def load_config(config_path: Path) -> SimConfig:
    """Load ``sim.yaml`` and its ground-truth file into a validated :class:`SimConfig`."""
    config_path = Path(config_path)
    raw = _read_yaml(config_path)
    gt_path = config_path.parent / raw.get("ground_truth_path", "ground_truth.yaml")
    gt = _read_yaml(gt_path)

    truth = GroundTruth(
        baseline_recovery={k: float(gt["baseline_recovery"][k]) for k in DECLINE_CODES},
        treatment_lift_abs={k: float(gt["treatment_lift_abs"][k]) for k in DECLINE_CODES},
        payday_known_extra_lift_abs=float(gt["payday_known_extra_lift_abs"]),
        billing_ticket_rate={
            k: float(gt["billing_ticket_rate"][k]) for k in ("control", "treatment")
        },
        involuntary_churn_given_unrecovered=float(gt["involuntary_churn_given_unrecovered"]),
        voluntary_churn_30d=float(gt["voluntary_churn_30d"]),
    )
    decline_mix = _check_mix("decline_mix", raw["decline_mix"])
    if set(decline_mix) != set(DECLINE_CODES):
        raise ValueError(f"decline_mix keys must be {DECLINE_CODES}")
    return SimConfig(
        seed=int(raw["seed"]),
        n_customers=int(raw["n_customers"]),
        country_mix=_check_mix("country_mix", raw["country_mix"]),
        plan_mix=_check_mix("plan_mix", raw["plan_mix"]),
        funding_mix=_check_mix("funding_mix", raw["funding_mix"]),
        brand_mix=_check_mix("brand_mix", raw["brand_mix"]),
        decline_mix=decline_mix,
        payday_known_rate=float(raw["payday_known_rate"]),
        pre_period_months=int(raw["pre_period_months"]),
        inject_srm=bool(raw.get("inject_srm", False)),
        truth=truth,
    )
