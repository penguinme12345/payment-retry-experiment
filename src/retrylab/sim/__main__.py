"""CLI: ``python -m retrylab.sim --config config/sim.yaml --out data/raw``."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from retrylab.sim.generator import generate


def _resolve(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    root = Path(os.environ.get("PROJECT_ROOT") or Path.cwd())
    return root / p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m retrylab.sim", description=__doc__)
    parser.add_argument("--config", default="config/sim.yaml", help="path to sim.yaml")
    parser.add_argument("--out", default="data/raw", help="output directory for Parquet files")
    args = parser.parse_args(argv)

    start = time.perf_counter()
    counts = generate(_resolve(args.config), _resolve(args.out))
    for table, rows in counts.items():
        print(f"{table:<26}{rows:>10,}")
    print(f"done in {time.perf_counter() - start:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
