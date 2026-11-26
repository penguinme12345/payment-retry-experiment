"""Fixtures for the dashboard tests: a throwaway PROJECT_ROOT populated from tests/app/fixtures."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest
from app_test_paths import FIXTURES, ProjectFactory


def _load_builder():
    path = FIXTURES / "build_warehouse.py"
    spec = importlib.util.spec_from_file_location("build_warehouse", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def warehouse_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The fixture DuckDB, built once per session."""
    return _load_builder().build(tmp_path_factory.mktemp("wh") / "warehouse.duckdb")


@pytest.fixture
def make_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, warehouse_file: Path
) -> ProjectFactory:
    """Create a PROJECT_ROOT with the chosen inputs and point the app at it."""

    def factory(
        results: str | None = "ship",
        warehouse: bool = True,
        power: bool = True,
        design_doc: bool = True,
    ) -> Path:
        root = tmp_path / "project"
        for sub in ("data", "reports", "docs"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        if warehouse:
            shutil.copy(warehouse_file, root / "data" / "warehouse.duckdb")
        if results is not None:
            shutil.copy(FIXTURES / f"results_{results}.json", root / "reports" / "results.json")
        if power:
            shutil.copy(FIXTURES / "power_analysis.json", root / "reports" / "power_analysis.json")
        if design_doc:
            shutil.copy(FIXTURES / "experiment_design.md", root / "docs" / "experiment_design.md")
        monkeypatch.setenv("PROJECT_ROOT", str(root))
        return root

    return factory
