# RetryLab one-command pipeline (PRD-F). Every target sees PROJECT_ROOT (contract C1).
export PROJECT_ROOT := $(CURDIR)

PYTHON     ?= python
SIM_CONFIG ?= config/sim.yaml

.PHONY: setup simulate dbt design analyze memo export all app test lint clean readme bullets

setup:
	$(PYTHON) -m pip install -e ".[dev]"

simulate:
	$(PYTHON) -m retrylab.sim --config $(SIM_CONFIG) --out data/raw

dbt:
	dbt build --project-dir dbt --profiles-dir dbt

design:
	$(PYTHON) -m retrylab.design --out reports/power_analysis.json

analyze:
	$(PYTHON) -m retrylab.analysis --db data/warehouse.duckdb --out reports/

memo:
	$(PYTHON) -m retrylab.reporting --results reports/results.json \
		--power reports/power_analysis.json --out docs/memo.md

export:
	$(PYTHON) -m app.export --out exports/powerbi/

all: simulate dbt design analyze memo export

app:
	streamlit run app/Home.py

test:
	pytest

lint:
	ruff check . && ruff format --check .

# Not in the PRD's target list: refresh README numbers / print resume bullets from results.json.
readme:
	$(PYTHON) -m retrylab.reporting.readme --results reports/results.json --readme README.md

bullets:
	$(PYTHON) -m retrylab.reporting.bullets --results reports/results.json

clean:
	rm -rf data/raw/*.parquet data/*.duckdb data/*.duckdb.wal \
		reports/*.json reports/figures/*.png exports/powerbi/*.csv docs/memo.md
