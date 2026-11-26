"""Build ``reports/power_analysis.json`` (contract C5) and the power-curve figure.

All inputs here are *design assumptions* fixed before the experiment ran. They come from the
historical (pre-period) decline mix and recovery rates, not from the experiment data, and this
module never reads ``config/ground_truth.yaml``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from retrylab.design.power import achieved_power, mde_for_n, required_n_per_arm

EXPERIMENT_ID = "retry_timing_v1"
PRIMARY_METRIC = "recovery_rate"

# Historical decline mix and per-code recovery under the fixed day-1/3/5/7 schedule.
# Blended baseline = Σ share × recovery = 0.345.
HISTORICAL_DECLINE_MIX: dict[str, tuple[float, float]] = {
    # decline_code: (share of failed invoices, historical recovery rate)
    "insufficient_funds": (0.45, 0.45),
    "expired_card": (0.20, 0.15),
    "do_not_honor": (0.20, 0.30),
    "generic_decline": (0.15, 0.35),
}

# Historical customer mix, used to size the pre-declared segment reads.
HISTORICAL_SEGMENT_MIX: dict[str, dict[str, float]] = {
    "plan_tier": {"basic": 0.55, "pro": 0.35, "business": 0.10},
    "card_funding": {"credit": 0.55, "debit": 0.38, "prepaid": 0.07},
    "country": {
        "US": 0.40,
        "CA": 0.08,
        "GB": 0.12,
        "DE": 0.10,
        "FR": 0.08,
        "BR": 0.08,
        "IN": 0.08,
        "AU": 0.06,
    },
}

MDE_CURVE_N: tuple[int, ...] = (2_500, 5_000, 10_000, 15_000, 20_000, 25_000)

GUARDRAILS: tuple[dict[str, Any], ...] = (
    {"metric": "billing_ticket_rate", "max_acceptable_increase_abs": 0.005},
    {"metric": "involuntary_churn_rate", "max_acceptable_increase_abs": 0.0},
)


@dataclass(frozen=True)
class DesignInputs:
    baseline_rate: float = 0.345
    mde_abs: float = 0.02
    alpha: float = 0.05
    power: float = 0.8
    two_sided: bool = True
    planned_n_per_arm: int = 25_000
    mde_curve_n: tuple[int, ...] = MDE_CURVE_N
    decline_mix: dict[str, tuple[float, float]] = field(
        default_factory=lambda: dict(HISTORICAL_DECLINE_MIX)
    )
    segment_mix: dict[str, dict[str, float]] = field(
        default_factory=lambda: {k: dict(v) for k, v in HISTORICAL_SEGMENT_MIX.items()}
    )


def project_root() -> Path:
    return Path(os.environ.get("PROJECT_ROOT") or Path.cwd())


def _r(x: float, nd: int = 4) -> float:
    return round(float(x), nd)


def blended_baseline(decline_mix: dict[str, tuple[float, float]]) -> float:
    """Σ share × recovery over decline codes."""
    total_share = sum(s for s, _ in decline_mix.values())
    if abs(total_share - 1.0) > 1e-9:
        raise ValueError(f"decline mix shares must sum to 1, got {total_share}")
    return sum(s * r for s, r in decline_mix.values())


def _segment_rows(inp: DesignInputs) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code, (share, rate) in inp.decline_mix.items():
        rows.append(("initial_decline_code", code, share, rate))
    for dim, mix in inp.segment_mix.items():
        for value, share in mix.items():
            rows.append((dim, value, share, inp.baseline_rate))
    out = []
    for dim, value, share, rate in rows:
        n = int(round(share * inp.planned_n_per_arm))
        out.append(
            {
                "dimension": dim,
                "value": value,
                "share": _r(share, 4),
                "baseline_rate": _r(rate, 4),
                "n_per_arm": n,
                "mde_abs": _r(mde_for_n(rate, n, inp.alpha, inp.power, inp.two_sided)),
            }
        )
    return out


def build_power_analysis(inp: DesignInputs | None = None) -> dict[str, Any]:
    """Compute the C5 payload. Keys and types follow ``01_CONTRACTS.md`` § C5.

    Two additive keys (``baseline_components`` and ``segment_mde``) document where the baseline
    comes from and how well the pre-declared segments are powered; consumers can ignore them.
    """
    inp = inp or DesignInputs()
    blended = blended_baseline(inp.decline_mix)
    if abs(blended - inp.baseline_rate) > 1e-9:
        raise ValueError(f"baseline_rate {inp.baseline_rate} != blended decline mix {blended}")

    n_req = required_n_per_arm(inp.baseline_rate, inp.mde_abs, inp.alpha, inp.power, inp.two_sided)
    pw = achieved_power(
        inp.baseline_rate, inp.mde_abs, inp.planned_n_per_arm, inp.alpha, inp.two_sided
    )
    curve = [
        {
            "n_per_arm": int(n),
            "mde_abs": _r(mde_for_n(inp.baseline_rate, n, inp.alpha, inp.power, inp.two_sided)),
        }
        for n in inp.mde_curve_n
    ]
    return {
        "experiment_id": EXPERIMENT_ID,
        "primary_metric": PRIMARY_METRIC,
        "baseline_rate": float(inp.baseline_rate),
        "mde_abs": float(inp.mde_abs),
        "alpha": float(inp.alpha),
        "power": float(inp.power),
        "two_sided": bool(inp.two_sided),
        "required_n_per_arm": int(n_req),
        "planned_n_per_arm": int(inp.planned_n_per_arm),
        "achieved_power_at_mde": _r(pw),
        "mde_curve": curve,
        "guardrails": [dict(g) for g in GUARDRAILS],
        "baseline_components": [
            {"decline_code": code, "share": _r(s), "recovery_rate": _r(r)}
            for code, (s, r) in inp.decline_mix.items()
        ],
        "segment_mde": _segment_rows(inp),
    }


def write_power_analysis(payload: dict[str, Any], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def plot_power_curve(payload: dict[str, Any], out: Path) -> Path:
    """MDE vs. n per arm, with the planned n and the target MDE marked."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker
    import numpy as np

    p = payload["baseline_rate"]
    alpha = payload["alpha"]
    power = payload["power"]
    two_sided = payload["two_sided"]
    planned = payload["planned_n_per_arm"]
    ns = np.linspace(1_000, 30_000, 120)
    mdes = [mde_for_n(p, n, alpha, power, two_sided) * 100 for n in ns]
    mde_planned = mde_for_n(p, planned, alpha, power, two_sided) * 100

    plt.rcParams["svg.hashsalt"] = "retrylab"
    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    ax.plot(ns, mdes, color="#3366CC", lw=2, label="Minimum detectable effect")
    ax.scatter(
        [pt["n_per_arm"] for pt in payload["mde_curve"]],
        [pt["mde_abs"] * 100 for pt in payload["mde_curve"]],
        color="#3366CC",
        zorder=3,
        s=18,
    )
    ax.axhline(
        payload["mde_abs"] * 100,
        color="#8A8F98",
        ls="--",
        lw=1,
        label=f"Target MDE ({payload['mde_abs'] * 100:.1f}pp)",
    )
    ax.axvline(
        payload["required_n_per_arm"],
        color="#8A8F98",
        ls=":",
        lw=1,
        label=f"Required n ({payload['required_n_per_arm']:,}/arm)",
    )
    ax.axvline(
        planned,
        color="#222222",
        lw=1.2,
        label=f"Planned n ({planned:,}/arm, MDE {mde_planned:.2f}pp)",
    )
    ax.set_xlabel("Invoices per arm")
    ax.set_ylabel("Minimum detectable lift in recovery rate (pp)")
    ax.set_title(
        f"At {planned:,} per arm we can detect a {mde_planned:.2f}pp lift "
        f"(baseline {p * 100:.1f}%, α={alpha}, power={power:.0%})"
    )
    ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
    ax.set_xlim(0, 30_000)
    ax.set_ylim(0, max(mdes) * 1.05)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper center")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, metadata={"Software": None})
    plt.close(fig)
    return out
