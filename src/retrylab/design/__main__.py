"""CLI: ``python -m retrylab.design --out reports/power_analysis.json``."""

from __future__ import annotations

import argparse
from pathlib import Path

from retrylab.design.report import (
    build_power_analysis,
    plot_power_curve,
    project_root,
    write_power_analysis,
)


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else project_root() / path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="retrylab.design", description=__doc__)
    ap.add_argument("--out", default="reports/power_analysis.json", help="C5 JSON output path")
    ap.add_argument(
        "--figure", default="reports/figures/power_curve.png", help="power curve PNG path"
    )
    ap.add_argument("--no-figure", action="store_true", help="skip the PNG")
    args = ap.parse_args(argv)

    payload = build_power_analysis()
    out = write_power_analysis(payload, _resolve(args.out))
    print(f"wrote {out}")
    if not args.no_figure:
        fig = plot_power_curve(payload, _resolve(args.figure))
        print(f"wrote {fig}")
    print(
        f"required n/arm = {payload['required_n_per_arm']:,}; "
        f"power at planned n = {payload['achieved_power_at_mde']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
