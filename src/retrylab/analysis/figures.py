"""Matplotlib figures for the results (150 dpi, 8×5 in, gray/blue colorblind-safe palette)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CONTROL = "#8A8F98"
TREATMENT = "#3366CC"
DPI = 150
SIZE = (8, 5)


def _style(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(length=3)


def _save(fig: plt.Figure, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, metadata={"Software": None})
    plt.close(fig)
    return path


def _pp(x: float) -> str:
    return f"{x * 100:+.1f}pp"


def lift_overall(results: dict[str, Any], path: Path) -> Path:
    """Primary-metric lift with 95% CI, raw vs. CUPED-adjusted."""
    p, c = results["primary"], results["cuped"]
    labels = ["Raw (z-test, Newcombe CI)", f"CUPED ({c['covariate']})"]
    est = np.array([p["abs_lift"], c["abs_lift"]]) * 100
    lo = np.array([p["ci_low"], c["ci_low"]]) * 100
    hi = np.array([p["ci_high"], c["ci_high"]]) * 100
    fig, ax = plt.subplots(figsize=SIZE)
    y = np.arange(len(labels))[::-1]
    ax.errorbar(est, y, xerr=[est - lo, hi - est], fmt="o", color=TREATMENT, capsize=6, ms=8)
    for yi, e, l_, h in zip(y, est, lo, hi, strict=True):
        ax.annotate(
            f"{e:+.2f}pp [{l_:+.2f}, {h:+.2f}]",
            (e, yi),
            xytext=(0, 12),
            textcoords="offset points",
            ha="center",
            fontsize=9,
        )
    ax.axvline(0, color=CONTROL, lw=1, ls="--")
    ax.set_yticks(y, labels)
    ax.set_ylim(-0.7, len(labels) - 0.3)
    ax.set_xlabel("Treatment − control recovery rate (percentage points, 95% CI)")
    verb = "lift" if p["abs_lift"] >= 0 else "change"
    sig = "" if p["significant"] else " (not significant)"
    ax.set_title(
        f"Smart retries {verb} recovery by {_pp(p['abs_lift'])}{sig}; "
        f"CUPED cuts variance {c['variance_reduction_pct']:.1f}%"
    )
    _style(ax)
    return _save(fig, path)


def segment_forest(results: dict[str, Any], path: Path) -> Path:
    """Forest plot of per-segment lift; BH-significant segments highlighted in blue."""
    segs = results["segments"]
    n = len(segs)
    fig, ax = plt.subplots(figsize=SIZE)
    y = np.arange(n)[::-1]
    for yi, s in zip(y, segs, strict=True):
        color = TREATMENT if s["significant_adj"] else CONTROL
        e, lo, hi = s["abs_lift"] * 100, s["ci_low"] * 100, s["ci_high"] * 100
        ax.plot([lo, hi], [yi, yi], color=color, lw=1.5)
        ax.plot([e], [yi], "o", color=color, ms=4)
    ax.axvline(0, color=CONTROL, lw=1, ls="--")
    ax.set_yticks(y, [f"{s['dimension']}: {s['value']}" for s in segs], fontsize=6)
    ax.set_xlabel("Treatment − control recovery rate (percentage points, 95% CI)")
    hits = [s for s in segs if s["significant_adj"]]
    if hits:
        top = max(hits, key=lambda s: abs(s["abs_lift"]))
        title = (
            f"{len(hits)} of {n} segments significant after BH; largest: "
            f"{top['value']} {_pp(top['abs_lift'])}"
        )
    else:
        title = f"No segment is significant after BH correction ({n} segments)"
    ax.set_title(title)
    ax.plot([], [], "o-", color=TREATMENT, label="Significant (BH q < 0.05)")
    ax.plot([], [], "o-", color=CONTROL, label="Not significant")
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    _style(ax)
    return _save(fig, path)


def recovery_by_day(df: pd.DataFrame, path: Path) -> Path:
    """Cumulative share of failed invoices recovered, by day since failure and variant."""
    days = np.linspace(0, 7, 7 * 24 + 1)
    fig, ax = plt.subplots(figsize=SIZE)
    finals: dict[str, float] = {}
    for variant, color in (("control", CONTROL), ("treatment", TREATMENT)):
        sub = df[df["variant"] == variant]
        hrs = sub.loc[sub["is_recovered"], "hours_to_recovery"].to_numpy(dtype=float)
        hrs = np.sort(hrs[~np.isnan(hrs)]) / 24.0
        curve = np.searchsorted(hrs, days, side="right") / max(len(sub), 1) * 100
        finals[variant] = float(sub["is_recovered"].mean() * 100)
        ax.step(days, curve, where="post", color=color, lw=2, label=variant.capitalize())
    ax.set_xlim(0, 7)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Days since initial payment failure")
    ax.set_ylabel("Cumulative invoices recovered (%)")
    gap = finals["treatment"] - finals["control"]
    ax.set_title(
        f"By day 7, smart retries recover {finals['treatment']:.1f}% vs. "
        f"{finals['control']:.1f}% ({gap:+.1f}pp)"
    )
    ax.legend(frameon=False, loc="lower right")
    _style(ax)
    return _save(fig, path)


def make_figures(results: dict[str, Any], df: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Write the three PRD-D figures into ``out_dir`` and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        lift_overall(results, out_dir / "lift_overall.png"),
        segment_forest(results, out_dir / "segment_forest.png"),
        recovery_by_day(df, out_dir / "recovery_by_day.png"),
    ]
