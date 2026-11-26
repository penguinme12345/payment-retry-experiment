"""Render ``docs/memo.md`` from ``results.json`` + ``power_analysis.json``."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined

from retrylab.reporting.context import build_context, load_json


def _lower_first(s: str) -> str:
    """Lower-case the first letter and drop a trailing period, for mid-sentence use."""
    s = s.strip().rstrip(".")
    if len(s) > 1 and s[1].isupper():  # leave acronyms like "USD" alone
        return s
    return s[:1].lower() + s[1:]


def _env() -> Environment:
    env = Environment(
        loader=PackageLoader("retrylab.reporting", "templates"),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    env.filters["lower_first"] = _lower_first
    return env


def _tidy(text: str) -> str:
    """Collapse runs of blank lines left by template conditionals; end with one newline."""
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def render_memo(
    results: dict[str, Any],
    power: dict[str, Any],
    figures_dir: Path | None = None,
    memo_dir: Path | None = None,
) -> str:
    """Return the memo as Markdown."""
    ctx = build_context(results, power, figures_dir=figures_dir, memo_dir=memo_dir)
    return _tidy(_env().get_template("memo.md.j2").render(c=ctx))


def write_memo(
    results_path: Path, power_path: Path, out_path: Path, figures_dir: Path | None = None
) -> str:
    """Render the memo from files and write it to ``out_path``. Returns the Markdown."""
    text = render_memo(
        load_json(results_path),
        load_json(power_path),
        figures_dir=figures_dir,
        memo_dir=out_path.parent,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text
