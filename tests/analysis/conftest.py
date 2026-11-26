"""Shared fixtures for the analysis tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures.make_fixture_db import make_invoices, write_fixture_db  # noqa: E402


@pytest.fixture(scope="session")
def fixture_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """4,000-invoice warehouse with +5pp in insufficient_funds, 0 elsewhere."""
    return write_fixture_db(make_invoices(), tmp_path_factory.mktemp("wh") / "warehouse.duckdb")
