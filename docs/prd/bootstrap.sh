#!/usr/bin/env bash
# Creates the RetryLab repo skeleton so parallel agents start from the same base.
# Usage: bash bootstrap.sh [target_dir]   (run from the folder containing the PRD files)
set -euo pipefail

TARGET="${1:-retrylab}"
PRD_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$TARGET"
cd "$TARGET"

mkdir -p config data/raw dbt app/pages exports/powerbi reports/figures docs/prd .github/workflows \
  src/retrylab/{sim,design,analysis,reporting} \
  tests/{sim,dbt,design,analysis,app,integration}

for pkg in "" sim design analysis reporting; do
  touch "src/retrylab/${pkg:+$pkg/}__init__.py"
done
touch app/__init__.py
for t in sim dbt design analysis app integration; do touch "tests/$t/__init__.py"; done
touch data/raw/.gitkeep reports/figures/.gitkeep exports/powerbi/.gitkeep

cat > pyproject.toml <<'EOF'
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "retrylab"
version = "0.1.0"
description = "Subscription payment recovery A/B experiment: simulation, dbt metrics layer, analysis, dashboard."
requires-python = ">=3.11"
dependencies = [
  "numpy>=1.26", "pandas>=2.2", "pyarrow>=15", "pyyaml>=6",
  "duckdb>=1.0", "dbt-core>=1.8,<1.10", "dbt-duckdb>=1.8,<1.10",
  "scipy>=1.12", "statsmodels>=0.14", "pydantic>=2.6",
  "matplotlib>=3.8", "plotly>=5.20", "streamlit>=1.35", "jinja2>=3.1",
]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.4", "hypothesis>=6.100"]
semantic = ["dbt-metricflow>=0.7"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["slow: end-to-end tests (deselect with -m 'not slow')"]
EOF

cat > .gitignore <<'EOF'
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
data/raw/*.parquet
data/*.duckdb
data/*.duckdb.wal
dbt/target/
dbt/logs/
dbt/dbt_packages/
reports/*.json
reports/figures/*.png
exports/powerbi/*.csv
docs/memo.md
HANDOFF-*.md
EOF

cp "$PRD_DIR"/*.md docs/prd/

echo "RetryLab skeleton created in $(pwd)"
echo "Next: python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]' && git init"
