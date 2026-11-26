"""Fill the README's generated blocks from ``results.json``:
``python -m retrylab.reporting.readme --results reports/results.json --readme README.md``.

Replaces the text between ``<!-- BEGIN:<name> -->`` and ``<!-- END:<name> -->`` markers, so every
number in the README traces back to the results file.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from retrylab.reporting import formatting as fmt
from retrylab.reporting.bullets import make_bullets
from retrylab.reporting.context import load_json
from retrylab.reporting.labels import segment_subject
from retrylab.reporting.paths import resolve

DECISION_TEXT = {
    "ship": "Ship to all customers",
    "ship_segmented": "Ship to targeted segments",
    "do_not_ship": "Do not ship",
}


def headline(results: dict[str, Any]) -> str:
    """One-line headline result."""
    p = results["primary"]
    annual = fmt.money(float(results["revenue_impact"]["annualized_incremental_revenue_usd"]))
    return (
        f"Smart retry timing moved payment recovery {fmt.pct(p['control'])} → "
        f"{fmt.pct(p['treatment'])} ({fmt.signed_pp(p['abs_lift'])}, 95% CI "
        f"{fmt.ci_pp(p['ci_low'], p['ci_high'])}), worth an estimated {annual}/yr."
    )


def key_results(results: dict[str, Any]) -> str:
    """A Markdown table of the key numbers."""
    p, cu, srm = results["primary"], results["cuped"], results["srm"]
    rows = [
        ("Decision", DECISION_TEXT[results["recommendation"]["decision"]]),
        (
            "Sample",
            f"{fmt.count(results['n_control'])} control / "
            f"{fmt.count(results['n_treatment'])} treatment",
        ),
        ("Recovery rate", f"{fmt.pct(p['control'])} → {fmt.pct(p['treatment'])}"),
        ("Lift (95% CI)", f"{fmt.signed_pp(p['abs_lift'])} {fmt.ci_pp(p['ci_low'], p['ci_high'])}"),
        (
            "CUPED lift (95% CI)",
            f"{fmt.signed_pp(cu['abs_lift'])} {fmt.ci_pp(cu['ci_low'], cu['ci_high'])}, "
            f"{fmt.plain_pct(cu['variance_reduction_pct'])} variance reduction",
        ),
        ("SRM check", f"{'passed' if srm['passed'] else 'FAILED'} ({fmt.pvalue(srm['p_value'])})"),
    ]
    for g in results.get("guardrails", []):
        rows.append(
            (
                g["metric"],
                f"{fmt.signed_pp(g['abs_lift'], 2)} ({'breached' if g['breached'] else 'held'})",
            )
        )
    best = sorted(
        (s for s in results.get("segments", []) if s["significant_adj"] and s["abs_lift"] > 0),
        key=lambda s: -s["abs_lift"],
    )[:2]
    for s in best:
        rows.append(
            (segment_subject(s["dimension"], s["value"]), f"{fmt.signed_pp(s['abs_lift'])} lift")
        )
    rows.append(
        (
            "Annualized impact",
            fmt.money(float(results["revenue_impact"]["annualized_incremental_revenue_usd"])),
        )
    )
    lines = ["| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines)


def blocks(results: dict[str, Any]) -> dict[str, str]:
    """All generated README blocks, by marker name."""
    return {
        "headline": headline(results),
        "key-results": key_results(results),
        "bullets": "\n".join(f"- {b}" for b in make_bullets(results)),
    }


def fill(readme_text: str, generated: dict[str, str]) -> str:
    """Replace each marked block's body with its generated content."""
    for name, body in generated.items():
        pattern = re.compile(
            rf"(<!-- BEGIN:{re.escape(name)} -->\n).*?(\n<!-- END:{re.escape(name)} -->)",
            re.DOTALL,
        )
        readme_text = pattern.sub(lambda m, b=body: m.group(1) + b + m.group(2), readme_text)
    return readme_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m retrylab.reporting.readme")
    parser.add_argument("--results", default="reports/results.json")
    parser.add_argument("--readme", default="README.md")
    args = parser.parse_args(argv)
    path: Path = resolve(args.readme)
    path.write_text(
        fill(path.read_text(encoding="utf-8"), blocks(load_json(resolve(args.results))))
    )
    print(f"updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
