"""Path resolution against ``PROJECT_ROOT`` (contract C1)."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """``$PROJECT_ROOT`` if set, else the current directory."""
    return Path(os.environ.get("PROJECT_ROOT") or Path.cwd())


def resolve(path: str | Path) -> Path:
    """Resolve a relative path against the project root; absolute paths pass through."""
    p = Path(path)
    return p if p.is_absolute() else project_root() / p
