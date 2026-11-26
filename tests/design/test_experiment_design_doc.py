"""``docs/experiment_design.md`` has all nine sections and only uses numbers from C5."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from retrylab.design.report import build_power_analysis

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "experiment_design.md"

SECTIONS = [
    "Background",
    "Hypothesis",
    "Unit of randomization and analysis",
    "Metrics",
    "Sample size and duration",
    "Analysis plan",
    "Decision rules",
    "Risks and mitigations",
    "Pre-registration statement",
]

# Contract constants (01_CONTRACTS.md § C2 / C6) that may appear without coming from C5.
CONTRACT_CONSTANTS = {"50,000", "0.001", "50/50"}

# Numbers worth checking: decimals, thousands-separated integers, and pp / % values.
NUMBER_RE = re.compile(r"(?<![\w.])[+−-]?(\d{1,3}(?:,\d{3})+|\d+\.\d+|\d+)(pp|%)?(?![\w.])")


def _walk_numbers(obj) -> list[float]:
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, dict):
        return [x for v in obj.values() for x in _walk_numbers(v)]
    if isinstance(obj, list):
        return [x for v in obj for x in _walk_numbers(v)]
    return []


def allowed_tokens(payload: dict) -> set[str]:
    values = set(_walk_numbers(payload))
    values.add(1.0 - payload["alpha"])  # confidence level of the CIs
    out = set(CONTRACT_CONSTANTS)
    for v in values:
        out.add(repr(v))
        out.add(f"{v:g}")
        if v == int(v):
            out.add(f"{int(v):,}")
            out.add(str(int(v)))
        for nd in (0, 1, 2):
            out.add(f"{v * 100:.{nd}f}%")
            out.add(f"{v * 100:.{nd}f}pp")
    return out


@pytest.fixture(scope="module")
def doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_all_nine_sections_present_in_order(doc):
    headings = re.findall(r"^## (\d)\. (.+)$", doc, flags=re.M)
    assert [int(n) for n, _ in headings] == list(range(1, 10))
    assert [t.strip() for _, t in headings] == SECTIONS


def test_every_number_comes_from_power_analysis(doc):
    allowed = allowed_tokens(build_power_analysis())
    bad = []
    for m in NUMBER_RE.finditer(doc):
        num, unit = m.group(1), m.group(2) or ""
        is_plain_small_int = not unit and "," not in num and "." not in num
        if is_plain_small_int:
            continue  # section numbers, "four retries", "30 days", years, etc.
        token = num + unit
        if token not in allowed:
            line = doc.count("\n", 0, m.start()) + 1
            bad.append(f"line {line}: {token}")
    assert not bad, "numbers not traceable to power_analysis.json:\n" + "\n".join(bad)


def test_headline_numbers_present(doc):
    p = build_power_analysis()
    assert f"{p['required_n_per_arm']:,}" in doc
    assert f"{p['planned_n_per_arm']:,}" in doc
    assert f"{p['achieved_power_at_mde'] * 100:.1f}%" in doc
    for pt in p["mde_curve"]:
        assert f"{pt['n_per_arm']:,}" in doc
        assert f"{pt['mde_abs'] * 100:.2f}pp" in doc


def test_dbt_metric_names_referenced(doc):
    for name in (
        "recovery_rate",
        "recovered_revenue_per_invoice",
        "billing_ticket_rate",
        "involuntary_churn_rate",
        "experiment_invoices",
        "pre_failed_attempt_rate",
    ):
        assert f"`{name}`" in doc


def test_design_code_never_loads_ground_truth():
    src = (ROOT / "src" / "retrylab" / "design").rglob("*.py")
    for f in src:
        text = f.read_text()
        assert "ground_truth.yaml'" not in text and 'ground_truth.yaml"' not in text, f
