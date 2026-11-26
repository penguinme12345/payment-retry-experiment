"""Paths and constants shared by the dashboard tests."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "app"
PAGES = {
    "overview": APP_DIR / "Home.py",
    "segments": APP_DIR / "pages" / "1_Segments.py",
    "guardrails": APP_DIR / "pages" / "2_Guardrails.py",
    "explore": APP_DIR / "pages" / "3_Explore.py",
    "methodology": APP_DIR / "pages" / "4_Methodology.py",
}
RESULTS_VARIANTS = ("ship", "ship_segmented", "guardrail_breached", "srm_failed")

ProjectFactory = Callable[..., Path]

# tests/app has no __init__.py (a package named ``app`` there would shadow the real one), so make
# sure the repo root is importable for ``import app``.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
