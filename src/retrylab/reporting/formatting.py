"""Number formatting helpers for the memo, README, and resume bullets.

Conventions (PRD-F §1.2):
- percentage points: ``3.2pp`` (``signed_pp`` gives ``+3.2pp`` / ``-0.4pp``)
- rates: ``34.5%``
- money: ``$1.2M`` / ``$48,300`` / ``$8.75``
- confidence intervals: ``[2.4pp, 4.0pp]``
"""

from __future__ import annotations

import math


def _clean_zero(x: float, digits: int) -> float:
    """Avoid printing ``-0.0`` for values that round to zero."""
    rounded = round(x, digits)
    return 0.0 if rounded == 0 else rounded


def pp(x: float, digits: int = 1) -> str:
    """A proportion difference as percentage points: ``0.032 -> '3.2pp'``."""
    return f"{_clean_zero(x * 100, digits):.{digits}f}pp"


def signed_pp(x: float, digits: int = 1) -> str:
    """Like :func:`pp` but always signed: ``0.032 -> '+3.2pp'``, ``-0.004 -> '-0.4pp'``."""
    v = _clean_zero(x * 100, digits)
    sign = "+" if v >= 0 else "-"
    return f"{sign}{abs(v):.{digits}f}pp"


def pct(x: float, digits: int = 1) -> str:
    """A rate as a percentage: ``0.345 -> '34.5%'``."""
    return f"{_clean_zero(x * 100, digits):.{digits}f}%"


def plain_pct(x: float, digits: int = 1) -> str:
    """A number that is already a percentage: ``18.5 -> '18.5%'``."""
    return f"{_clean_zero(x, digits):.{digits}f}%"


def money(x: float) -> str:
    """USD with scale-aware precision.

    ``>= $1M`` -> ``$1.2M``; ``>= $1,000`` -> nearest $100 with separators (``$48,300``);
    below that -> cents (``$8.75``).
    """
    sign = "-" if x < 0 else ""
    a = abs(x)
    if a >= 999_950:
        return f"{sign}${a / 1_000_000:.1f}M"
    if a >= 1_000:
        return f"{sign}${int(round(a, -2)):,}"
    if round(a, 2) == 0:
        return "$0.00"
    return f"{sign}${a:.2f}"


def signed_money(x: float) -> str:
    """Money with an explicit sign: ``0.42 -> '+$0.42'``."""
    s = money(x)
    return s if s.startswith("-") else f"+{s}"


def ci_pp(low: float, high: float, digits: int = 1) -> str:
    """A CI on a proportion difference: ``[2.4pp, 4.0pp]``."""
    return f"[{pp(low, digits)}, {pp(high, digits)}]"


def ci_money(low: float, high: float) -> str:
    """A CI on a money difference: ``[$0.31, $0.55]``."""
    return f"[{money(low)}, {money(high)}]"


def pvalue(p: float) -> str:
    """``p < 0.001`` for tiny values, otherwise ``p = 0.034``."""
    if p is None or math.isnan(p):
        return "p = n/a"
    if p < 0.001:
        return "p < 0.001"
    return f"p = {p:.3f}"


def count(n: int) -> str:
    """An integer with thousands separators: ``25000 -> '25,000'``."""
    return f"{int(n):,}"
