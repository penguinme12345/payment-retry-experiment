"""Run dbt on the hand-built fixtures and check the marts against `expected/*.csv` exactly."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "raw"
EXPECTED = HERE / "expected"

sys.path.insert(0, str(HERE))
from build_fixtures import CASES  # noqa: E402

# Contract C4: column names and DuckDB types, in order.
FCT_SCHEMA = {
    "invoice_id": "VARCHAR",
    "customer_id": "VARCHAR",
    "variant": "VARCHAR",
    "country": "VARCHAR",
    "plan_tier": "VARCHAR",
    "card_funding": "VARCHAR",
    "initial_decline_code": "VARCHAR",
    "amount_usd": "DOUBLE",
    "failed_at": "TIMESTAMP",
    "is_recovered": "BOOLEAN",
    "recovered_at": "TIMESTAMP",
    "hours_to_recovery": "DOUBLE",
    "retries_attempted": "INTEGER",
    "recovered_amount_usd": "DOUBLE",
    "had_billing_ticket_14d": "BOOLEAN",
    "churned_involuntary_30d": "BOOLEAN",
    "pre_paid_invoice_count": "INTEGER",
    "pre_failed_attempt_rate": "DOUBLE",
}
SUMMARY_SCHEMA = {
    "variant": "VARCHAR",
    "n_invoices": "INTEGER",
    "n_recovered": "INTEGER",
    "recovery_rate": "DOUBLE",
    "recovered_revenue_usd": "DOUBLE",
    "recovered_revenue_per_invoice_usd": "DOUBLE",
    "avg_retries_per_invoice": "DOUBLE",
    "billing_ticket_rate": "DOUBLE",
    "involuntary_churn_rate": "DOUBLE",
}
SEGMENTS_SCHEMA = {
    "variant": "VARCHAR",
    "segment_dimension": "VARCHAR",
    "segment_value": "VARCHAR",
    "n_invoices": "INTEGER",
    "n_recovered": "INTEGER",
    "recovery_rate": "DOUBLE",
    "recovered_revenue_per_invoice_usd": "DOUBLE",
}
CONTRACT_METRICS = {
    "recovery_rate",
    "recovered_revenue",
    "recovered_revenue_per_invoice",
    "avg_retries_per_invoice",
    "billing_ticket_rate",
    "involuntary_churn_rate",
    "experiment_invoices",
}
SORT_KEYS = {
    "fct_experiment_invoices": ["invoice_id"],
    "agg_experiment_summary": ["variant"],
    "agg_experiment_segments": ["variant", "segment_dimension", "segment_value"],
}


def _dbt(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    dbt = shutil.which("dbt") or str(Path(sys.executable).parent / "dbt")
    env = {**os.environ, "PROJECT_ROOT": str(root), "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    cmd = [
        dbt,
        *args,
        "--project-dir", str(REPO / "dbt"),
        "--profiles-dir", str(REPO / "dbt"),
        "--target-path", str(root / "target"),
        "--log-path", str(root / "logs"),
    ]  # fmt: skip
    return subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, check=False)


@pytest.fixture(scope="session")
def warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the dbt project on the fixtures into a throwaway PROJECT_ROOT."""
    root = tmp_path_factory.mktemp("dbt_root")
    (root / "data").mkdir()
    vars_ = json.dumps({"raw_dir": str(FIXTURES)})
    proc = _dbt(["build", "--vars", vars_], root)
    assert proc.returncode == 0, proc.stdout[-5000:] + proc.stderr[-2000:]
    return root


@pytest.fixture(scope="session")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(str(warehouse / "data" / "warehouse.duckdb"), read_only=True)
    yield c
    c.close()


def _read(con: duckdb.DuckDBPyConnection, table: str) -> pd.DataFrame:
    keys = ", ".join(SORT_KEYS[table])
    return con.execute(f"select * from main.{table} order by {keys}").df()


def _expected(table: str, schema: dict[str, str]) -> pd.DataFrame:
    df = pd.read_csv(EXPECTED / f"{table}.csv", keep_default_na=True)
    for col, typ in schema.items():
        if typ == "TIMESTAMP":
            df[col] = pd.to_datetime(df[col])
        elif typ == "BOOLEAN":
            df[col] = df[col].astype(bool)
        elif typ == "VARCHAR":
            df[col] = df[col].astype(str)
    return df.sort_values(SORT_KEYS[table]).reset_index(drop=True)


def _normalise(df: pd.DataFrame, schema: dict[str, str]) -> pd.DataFrame:
    out = df.copy()
    for col, typ in schema.items():
        if typ == "TIMESTAMP":
            out[col] = pd.to_datetime(out[col]).astype("datetime64[us]")
        elif typ in ("DOUBLE", "INTEGER"):
            out[col] = out[col].astype("float64").round(10)
        elif typ == "BOOLEAN":
            out[col] = out[col].astype(bool)
        else:
            out[col] = out[col].astype(str)
    return out.reset_index(drop=True)


def test_dbt_build_passes(warehouse: Path) -> None:
    results = json.loads((warehouse / "target" / "run_results.json").read_text())["results"]
    bad = [r["unique_id"] for r in results if r["status"] not in ("success", "pass")]
    assert not bad, bad
    assert sum(r["unique_id"].startswith("test.") for r in results) >= 50


@pytest.mark.parametrize(
    ("table", "schema"),
    [
        ("fct_experiment_invoices", FCT_SCHEMA),
        ("agg_experiment_summary", SUMMARY_SCHEMA),
        ("agg_experiment_segments", SEGMENTS_SCHEMA),
    ],
)
def test_mart_schema_matches_contract(
    con: duckdb.DuckDBPyConnection, table: str, schema: dict[str, str]
) -> None:
    rows = con.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema = 'main' and table_name = ? order by ordinal_position",
        [table],
    ).fetchall()
    assert dict(rows) == schema
    assert [r[0] for r in rows] == list(schema)
    kind = con.execute(
        "select table_type from information_schema.tables "
        "where table_schema = 'main' and table_name = ?",
        [table],
    ).fetchone()
    assert kind == ("BASE TABLE",)


@pytest.mark.parametrize(
    ("table", "schema"),
    [
        ("fct_experiment_invoices", FCT_SCHEMA),
        ("agg_experiment_summary", SUMMARY_SCHEMA),
        ("agg_experiment_segments", SEGMENTS_SCHEMA),
    ],
)
def test_mart_matches_expected(
    con: duckdb.DuckDBPyConnection, table: str, schema: dict[str, str]
) -> None:
    actual = _normalise(_read(con, table), schema)
    expected = _normalise(_expected(table, schema), schema)
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False, check_exact=True)


@pytest.mark.parametrize("idx", range(len(CASES)), ids=[c.note for c in CASES])
def test_edge_case(con: duckdb.DuckDBPyConnection, idx: int) -> None:
    """Each fixture customer is one edge case; check its fact row field by field."""
    case = CASES[idx]
    cid = f"cus_{idx + 1:06d}"
    row = con.execute(
        "select is_recovered, hours_to_recovery, retries_attempted, recovered_amount_usd, "
        "had_billing_ticket_14d, churned_involuntary_30d, pre_paid_invoice_count, "
        "pre_failed_attempt_rate from main.fct_experiment_invoices where customer_id = ?",
        [cid],
    ).fetchone()
    assert row is not None, cid
    recovered, hours, retries, amount, ticket, churn, pre_paid, pre_rate = row
    assert recovered is case.exp_recovered
    assert hours == case.exp_hours
    assert retries == len(case.retries)
    assert (amount > 0) is case.exp_recovered
    assert ticket is case.exp_ticket
    assert churn is case.exp_churn
    assert pre_paid == case.exp_pre_paid
    assert pre_rate == pytest.approx(case.exp_pre_rate, abs=1e-12)


def test_time_spine(con: duckdb.DuckDBPyConnection) -> None:
    lo, hi, n = con.execute(
        "select min(date_day), max(date_day), count(*) from main.metricflow_time_spine"
    ).fetchone()
    assert (str(lo), str(hi), n) == ("2025-01-01", "2026-12-31", 730)


def test_semantic_manifest(warehouse: Path) -> None:
    """`dbt parse` writes a semantic manifest with the contract metrics, each documented."""
    proc = _dbt(["parse"], warehouse)
    assert proc.returncode == 0, proc.stdout[-3000:]
    manifest = json.loads((warehouse / "target" / "semantic_manifest.json").read_text())
    metrics = {m["name"]: m for m in manifest["metrics"]}
    assert set(metrics) >= CONTRACT_METRICS
    for name in CONTRACT_METRICS:
        assert len(metrics[name]["description"]) > 80, name
    assert metrics["recovery_rate"]["type"] == "ratio"
    assert metrics["experiment_invoices"]["type"] == "simple"
    (model,) = manifest["semantic_models"]
    entities = {e["name"]: e["type"] for e in model["entities"]}
    assert entities == {"invoice": "primary", "customer": "foreign"}
    dims = {d["name"] for d in model["dimensions"]}
    assert {"failed_at", "variant", "country", "plan_tier", "card_funding",
            "initial_decline_code"} <= dims  # fmt: skip


@pytest.mark.skipif(shutil.which("mf") is None, reason="dbt-metricflow not installed")
def test_metricflow_validate_configs(warehouse: Path) -> None:
    env = {**os.environ, "PROJECT_ROOT": str(warehouse), "DBT_PROFILES_DIR": str(REPO / "dbt")}
    proc = subprocess.run(
        ["mf", "validate-configs", "--skip-dw"],
        cwd=REPO / "dbt",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
