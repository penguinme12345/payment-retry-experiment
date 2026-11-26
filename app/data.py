"""Data access for the RetryLab dashboard.

Every page reads its inputs through this module. Paths resolve from ``PROJECT_ROOT`` (falling
back to the current working directory), DuckDB is always opened read-only, and every loader
returns ``None`` when its input is missing so pages can show a friendly warning instead of
crashing. Nothing here reads ``config/ground_truth.yaml``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import streamlit as st

EXPERIMENT_ID = "retry_timing_v1"
VARIANTS = ("control", "treatment")
COLORS = {"control": "#8A8F98", "treatment": "#3366CC"}
SEGMENT_DIMENSIONS = ("country", "plan_tier", "card_funding", "initial_decline_code")
DIMENSION_LABELS = {
    "country": "Country",
    "plan_tier": "Plan tier",
    "card_funding": "Card funding",
    "initial_decline_code": "Decline code",
}

# Input name -> (path relative to PROJECT_ROOT, make target(s) that produce it).
INPUTS: dict[str, tuple[str, str]] = {
    "warehouse": ("data/warehouse.duckdb", "make simulate dbt"),
    "results": ("reports/results.json", "make analyze"),
    "power": ("reports/power_analysis.json", "make design"),
    "design_doc": ("docs/experiment_design.md", "make design"),
}

FACT_TABLE = "fct_experiment_invoices"
SUMMARY_TABLE = "agg_experiment_summary"
SEGMENTS_TABLE = "agg_experiment_segments"
RECOVERY_WINDOW_HOURS = 7 * 24


def project_root() -> Path:
    """Return the repo root from ``PROJECT_ROOT``, or the current working directory."""
    env = os.environ.get("PROJECT_ROOT")
    return Path(env) if env else Path.cwd()


def input_path(name: str) -> Path:
    """Absolute path of a named input (see ``INPUTS``)."""
    return project_root() / INPUTS[name][0]


def make_target(name: str) -> str:
    """The make target(s) that produce a named input."""
    return INPUTS[name][1]


def missing_message(name: str) -> str:
    """A friendly message explaining which input is missing and how to create it."""
    rel, target = INPUTS[name]
    return f"`{rel}` was not found under `{project_root()}`. Run `{target}` to create it."


def warn_missing(name: str) -> None:
    """Show ``st.warning`` for a missing input."""
    st.warning(missing_message(name), icon="⚠️")


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


# --- JSON reports -------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def _read_json(path: str, mtime: float) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_results() -> dict[str, Any] | None:
    """``reports/results.json`` (contract C6), or ``None`` if missing or unreadable."""
    path = input_path("results")
    mtime = _mtime(path)
    return None if mtime is None else _read_json(str(path), mtime)


def load_power() -> dict[str, Any] | None:
    """``reports/power_analysis.json`` (contract C5), or ``None`` if missing or unreadable."""
    path = input_path("power")
    mtime = _mtime(path)
    return None if mtime is None else _read_json(str(path), mtime)


def load_design_doc() -> str | None:
    """Text of ``docs/experiment_design.md``, or ``None`` if missing."""
    path = input_path("design_doc")
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


# --- Warehouse ----------------------------------------------------------------------------


def warehouse_available() -> bool:
    """True when the DuckDB warehouse exists."""
    return input_path("warehouse").is_file()


def query(sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame | None:
    """Run a read-only query against the warehouse. ``None`` if the DB or table is missing."""
    path = input_path("warehouse")
    mtime = _mtime(path)
    if mtime is None:
        return None
    return _query(str(path), mtime, sql, tuple(params or ()))


def run_query(path: str, sql: str, params: Sequence[Any] = ()) -> pd.DataFrame | None:
    """Uncached read-only query against the DuckDB file at ``path``."""
    try:
        con = duckdb.connect(path, read_only=True)
    except duckdb.Error:
        return None
    try:
        return con.execute(sql, list(params)).df()
    except duckdb.Error:
        return None
    finally:
        con.close()


@st.cache_data(show_spinner=False)
def _query(path: str, mtime: float, sql: str, params: tuple[Any, ...]) -> pd.DataFrame | None:
    return run_query(path, sql, params)


def load_summary() -> pd.DataFrame | None:
    """``agg_experiment_summary`` ordered control, treatment."""
    return query(summary_sql())


def load_mart_segments() -> pd.DataFrame | None:
    """``agg_experiment_segments`` (descriptive per-variant segment rates)."""
    return query(
        f"SELECT * FROM {SEGMENTS_TABLE} ORDER BY segment_dimension, segment_value, variant"
    )


def load_filter_options() -> dict[str, list[str]] | None:
    """Distinct values of each segment dimension in the fact table."""
    options: dict[str, list[str]] = {}
    for dim in SEGMENT_DIMENSIONS:
        df = query(
            f"SELECT DISTINCT {dim} AS v FROM {FACT_TABLE} WHERE {dim} IS NOT NULL ORDER BY 1"
        )
        if df is None:
            return None
        options[dim] = [str(v) for v in df["v"].tolist()]
    return options


def _where(filters: dict[str, Sequence[str]]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for dim, values in filters.items():
        if dim not in SEGMENT_DIMENSIONS or not values:
            continue
        clauses.append(f"{dim} IN ({', '.join('?' for _ in values)})")
        params.extend(values)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def filtered_recovery(filters: dict[str, Sequence[str]]) -> pd.DataFrame | None:
    """Descriptive recovery stats by variant for the filtered fact table."""
    where, params = _where(filters)
    sql = f"""
        SELECT variant,
               COUNT(*) AS n_invoices,
               SUM(CASE WHEN is_recovered THEN 1 ELSE 0 END) AS n_recovered,
               AVG(CASE WHEN is_recovered THEN 1.0 ELSE 0.0 END) AS recovery_rate,
               SUM(recovered_amount_usd) AS recovered_revenue_usd,
               AVG(recovered_amount_usd) AS recovered_revenue_per_invoice_usd,
               AVG(retries_attempted) AS avg_retries_per_invoice
        FROM {FACT_TABLE}{where}
        GROUP BY variant ORDER BY variant
    """
    return query(sql, params)


def filtered_recovery_curve(filters: dict[str, Sequence[str]]) -> pd.DataFrame | None:
    """Cumulative share of invoices recovered by hour since failure (0..168), per variant."""
    where, params = _where(filters)
    sql = f"""
        WITH base AS (SELECT * FROM {FACT_TABLE}{where}),
        totals AS (SELECT variant, COUNT(*) AS n FROM base GROUP BY variant),
        hours AS (SELECT range AS hour FROM range(0, {RECOVERY_WINDOW_HOURS + 1})),
        rec AS (
            SELECT variant, CAST(CEIL(hours_to_recovery) AS INTEGER) AS hour, COUNT(*) AS k
            FROM base WHERE is_recovered AND hours_to_recovery IS NOT NULL
            GROUP BY 1, 2
        )
        SELECT t.variant, h.hour,
               COALESCE(SUM(r.k), 0) * 1.0 / t.n AS cumulative_recovery_rate
        FROM totals t CROSS JOIN hours h
        LEFT JOIN rec r ON r.variant = t.variant AND r.hour <= h.hour
        GROUP BY t.variant, h.hour, t.n
        ORDER BY t.variant, h.hour
    """
    return query(sql, params)


def filtered_retries(filters: dict[str, Sequence[str]]) -> pd.DataFrame | None:
    """Distribution of ``retries_attempted`` per variant (counts and within-variant share)."""
    where, params = _where(filters)
    sql = f"""
        SELECT variant, retries_attempted, COUNT(*) AS n_invoices,
               COUNT(*) * 1.0 / SUM(COUNT(*)) OVER (PARTITION BY variant) AS share
        FROM {FACT_TABLE}{where}
        GROUP BY variant, retries_attempted
        ORDER BY variant, retries_attempted
    """
    return query(sql, params)


def fact_table_sql() -> str:
    """SQL for the full fact table (used by the Power BI export)."""
    return f"SELECT * FROM {FACT_TABLE} ORDER BY invoice_id"


def summary_sql() -> str:
    """SQL for the per-variant summary mart (used by the Power BI export)."""
    return f"SELECT * FROM {SUMMARY_TABLE} ORDER BY variant"
