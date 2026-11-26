"""CLI: ``python -m retrylab.analysis --db data/warehouse.duckdb --out reports/``."""

from __future__ import annotations

import argparse
import time
from datetime import datetime

from retrylab.analysis.run import run_analysis


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m retrylab.analysis", description=__doc__)
    parser.add_argument("--db", default="data/warehouse.duckdb", help="DuckDB warehouse (C4)")
    parser.add_argument("--out", default="reports/", help="output dir for results.json/figures")
    parser.add_argument(
        "--power",
        default=None,
        help="power_analysis.json (C5); defaults to <out>/power_analysis.json",
    )
    parser.add_argument(
        "--frozen-time",
        type=_parse_time,
        default=None,
        help="fix generated_at (ISO-8601, e.g. 2026-04-15T12:00:00Z) for deterministic output",
    )
    parser.add_argument("--no-figures", action="store_true", help="skip writing PNGs")
    args = parser.parse_args(argv)

    start = time.perf_counter()
    power = args.power or f"{args.out.rstrip('/')}/power_analysis.json"
    res = run_analysis(args.db, args.out, power, args.frozen_time, not args.no_figures)
    p = res["primary"]
    print(
        f"n={res['n_control']}/{res['n_treatment']}  SRM {'ok' if res['srm']['passed'] else 'FAIL'}"
        f"  lift {p['abs_lift'] * 100:+.2f}pp [{p['ci_low'] * 100:+.2f}, {p['ci_high'] * 100:+.2f}]"
        f"  p={p['p_value']:.3g}  → {res['recommendation']['decision']}"
    )
    print(f"done in {time.perf_counter() - start:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
