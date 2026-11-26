"""Render every dashboard page against the fixtures with streamlit's AppTest."""

from __future__ import annotations

import pytest
from app_test_paths import PAGES, RESULTS_VARIANTS, ProjectFactory
from streamlit.testing.v1 import AppTest

TIMEOUT = 60


def run(page: str) -> AppTest:
    at = AppTest.from_file(str(PAGES[page]), default_timeout=TIMEOUT)
    at.run()
    return at


def texts(elements) -> str:
    return "\n".join(str(e.value) for e in elements)


@pytest.mark.parametrize("variant", RESULTS_VARIANTS)
@pytest.mark.parametrize("page", list(PAGES))
def test_every_page_renders_without_exceptions(
    page: str, variant: str, make_project: ProjectFactory
) -> None:
    make_project(results=variant)
    at = run(page)
    assert not at.exception, at.exception
    assert not at.warning or page == "explore", texts(at.warning)


@pytest.mark.parametrize(
    ("variant", "element", "expected"),
    [
        ("ship", "success", "Decision: SHIP smart retries to all customers"),
        ("ship_segmented", "info", "Decision: SHIP SEGMENTED"),
        ("guardrail_breached", "error", "Decision: DON'T SHIP"),
        ("srm_failed", "error", "Decision: DON'T SHIP"),
    ],
)
def test_decision_banner(
    variant: str, element: str, expected: str, make_project: ProjectFactory
) -> None:
    make_project(results=variant)
    at = run("overview")
    assert expected in texts(getattr(at, element))


def test_overview_kpis(make_project: ProjectFactory) -> None:
    make_project()
    at = run("overview")
    labels = [m.label for m in at.metric]
    assert len(at.metric) == 5
    assert labels == [
        "Recovery rate, control",
        "Recovery rate, treatment",
        "Absolute lift",
        "Annualized revenue impact",
        "Sample ratio check",
    ]
    assert at.metric[0].value == "31.5%"
    assert at.metric[2].value == "+2.2pp"
    assert at.metric[3].value == "$498,000"
    assert at.metric[4].value == "Passed"
    assert len(at.get("plotly_chart")) == 1


def test_overview_flags_srm_failure(make_project: ProjectFactory) -> None:
    make_project(results="srm_failed")
    at = run("overview")
    assert "Sample ratio mismatch detected" in texts(at.error)
    assert at.metric[4].value == "FAILED"


def test_segments_page(make_project: ProjectFactory) -> None:
    make_project(results="ship_segmented")
    at = run("segments")
    assert "Recommended to ship" in texts(at.success)
    assert "Decline code: insufficient_funds" in texts(at.success)
    assert len(at.selectbox) == 1
    assert len(at.dataframe) == 1
    assert len(at.dataframe[0].value) == 12
    at.selectbox[0].select("plan_tier").run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 3
    assert set(at.dataframe[0].value["Dimension"]) == {"plan_tier"}


def test_guardrails_page_shows_breach(make_project: ProjectFactory) -> None:
    make_project(results="guardrail_breached")
    at = run("guardrails")
    assert "Guardrail breached" in texts(at.error)
    table = at.dataframe[0].value
    assert list(table["Status"]) == ["BREACHED", "OK"]
    assert len(at.get("plotly_chart")) == 1


def test_guardrails_page_all_ok(make_project: ProjectFactory) -> None:
    make_project(results="ship")
    at = run("guardrails")
    assert "All 2 guardrails held" in texts(at.success)


def test_explore_filters(make_project: ProjectFactory) -> None:
    make_project()
    at = run("explore")
    assert "Descriptive only. See Segments for significance." in texts(at.warning)
    assert len(at.multiselect) == 4
    assert len(at.get("plotly_chart")) == 2
    total = at.dataframe[0].value["Invoices"].sum()
    assert total == 600
    at.multiselect(key="filter_initial_decline_code").select("insufficient_funds").run()
    assert not at.exception
    filtered = at.dataframe[0].value["Invoices"].sum()
    assert 0 < filtered < total


def test_methodology_page(make_project: ProjectFactory) -> None:
    make_project()
    at = run("methodology")
    labels = [m.label for m in at.metric]
    assert "Required n per arm" in labels
    assert at.metric[labels.index("Required n per arm")].value == "8,983"
    assert len(at.get("plotly_chart")) == 1
    assert "experiment_design.md" in texts(at.markdown)


@pytest.mark.parametrize("page", list(PAGES))
def test_missing_inputs_warn_instead_of_crashing(page: str, make_project: ProjectFactory) -> None:
    root = make_project(results=None, warehouse=False, power=False, design_doc=False)
    at = run(page)
    assert not at.exception, at.exception
    warnings = texts(at.warning)
    assert warnings, "expected a st.warning for missing inputs"
    assert "make " in warnings
    assert str(root) in warnings


def test_missing_warehouse_only(make_project: ProjectFactory) -> None:
    make_project(warehouse=False)
    at = run("guardrails")
    assert not at.exception
    assert "make simulate dbt" in texts(at.warning)
    # Falls back to results.json for the by-variant chart.
    assert len(at.get("plotly_chart")) == 1
