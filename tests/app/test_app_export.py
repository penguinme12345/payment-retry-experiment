"""Power BI CSV exports."""

from __future__ import annotations

import json

import duckdb
import pandas as pd
from app_test_paths import ProjectFactory

from app import export


def test_export_writes_all_files_with_matching_row_counts(make_project: ProjectFactory) -> None:
    root = make_project(results="ship_segmented")
    assert export.main(["--out", "exports/powerbi/"]) == 0
    out = root / "exports" / "powerbi"

    con = duckdb.connect(str(root / "data" / "warehouse.duckdb"), read_only=True)
    n_fact = con.execute("SELECT COUNT(*) FROM fct_experiment_invoices").fetchone()[0]
    n_summary = con.execute("SELECT COUNT(*) FROM agg_experiment_summary").fetchone()[0]
    con.close()
    results = json.loads((root / "reports" / "results.json").read_text())

    expected = {
        "experiment_invoices.csv": n_fact,
        "summary.csv": n_summary,
        "segments.csv": len(results["segments"]),
        "guardrails.csv": len(results["guardrails"]),
    }
    for name, n in expected.items():
        df = pd.read_csv(out / name)
        assert len(df) == n, name
        assert len(df.columns) > 0 and not any(str(c).startswith("Unnamed") for c in df.columns)

    invoices = pd.read_csv(out / "experiment_invoices.csv")
    assert "is_recovered" in invoices.columns and "variant" in invoices.columns
    segments = pd.read_csv(out / "segments.csv")
    assert list(segments.columns) == export.SEGMENT_COLUMNS
    assert segments["recommended_to_ship"].sum() == 2
    guardrails = pd.read_csv(out / "guardrails.csv")
    assert list(guardrails.columns) == export.GUARDRAIL_COLUMNS

    readme = (out / "README.md").read_text()
    assert "Recovery Rate =" in readme and "Recovery Lift (pp)" in readme


def test_export_is_deterministic(make_project: ProjectFactory) -> None:
    root = make_project()
    export.main(["--out", "a"])
    export.main(["--out", "b"])
    for name in ("experiment_invoices.csv", "summary.csv", "segments.csv", "guardrails.csv"):
        assert (root / "a" / name).read_bytes() == (root / "b" / name).read_bytes()


def test_export_with_missing_inputs_does_not_crash(make_project: ProjectFactory) -> None:
    root = make_project(results=None, warehouse=False)
    assert export.main(["--out", "exports/powerbi/"]) == 1
    assert (root / "exports" / "powerbi" / "README.md").is_file()
