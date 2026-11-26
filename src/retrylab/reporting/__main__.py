"""CLI: ``python -m retrylab.reporting --results reports/results.json
--power reports/power_analysis.json --out docs/memo.md``."""

from __future__ import annotations

import argparse

from retrylab.reporting.paths import resolve
from retrylab.reporting.render import write_memo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m retrylab.reporting", description=__doc__)
    parser.add_argument("--results", default="reports/results.json")
    parser.add_argument("--power", default="reports/power_analysis.json")
    parser.add_argument("--out", default="docs/memo.md")
    parser.add_argument("--figures", default="reports/figures", help="figures to embed if present")
    args = parser.parse_args(argv)

    out = resolve(args.out)
    text = write_memo(resolve(args.results), resolve(args.power), out, resolve(args.figures))
    print(f"wrote {out} ({len(text.split())} words)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
