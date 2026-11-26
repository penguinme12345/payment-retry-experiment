"""Number formatting helpers."""

from __future__ import annotations

import pytest

from retrylab.reporting import formatting as fmt


@pytest.mark.parametrize(
    ("x", "out"), [(0.032, "3.2pp"), (0.0, "0.0pp"), (-0.0004, "0.0pp"), (0.0612, "6.1pp")]
)
def test_pp(x: float, out: str) -> None:
    assert fmt.pp(x) == out


@pytest.mark.parametrize(("x", "out"), [(0.032, "+3.2pp"), (-0.004, "-0.4pp"), (-0.0001, "+0.0pp")])
def test_signed_pp(x: float, out: str) -> None:
    assert fmt.signed_pp(x) == out


def test_pct() -> None:
    assert fmt.pct(0.345) == "34.5%"
    assert fmt.pct(0.8, 0) == "80%"
    assert fmt.pct(0.0312, 2) == "3.12%"


@pytest.mark.parametrize(
    ("x", "out"),
    [
        (1_234_567, "$1.2M"),
        (999_999, "$1.0M"),
        (48_321, "$48,300"),
        (1_000, "$1,000"),
        (8.75, "$8.75"),
        (0.004, "$0.00"),
        (-2_500_000, "-$2.5M"),
    ],
)
def test_money(x: float, out: str) -> None:
    assert fmt.money(x) == out


def test_signed_money() -> None:
    assert fmt.signed_money(1.08) == "+$1.08"
    assert fmt.signed_money(-0.5) == "-$0.50"


def test_ci() -> None:
    assert fmt.ci_pp(0.024, 0.040) == "[2.4pp, 4.0pp]"
    assert fmt.ci_pp(-0.001, 0.016) == "[-0.1pp, 1.6pp]"
    assert fmt.ci_money(0.31, 0.55) == "[$0.31, $0.55]"


def test_pvalue() -> None:
    assert fmt.pvalue(1e-12) == "p < 0.001"
    assert fmt.pvalue(0.0344) == "p = 0.034"
    assert fmt.pvalue(float("nan")) == "p = n/a"


def test_count() -> None:
    assert fmt.count(25000) == "25,000"
