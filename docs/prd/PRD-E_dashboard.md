# PRD-E — Dashboard

**Owner paths:** `app/`, `exports/powerbi/`, `tests/app/`
**Consumes:** marts (C4), `reports/results.json` (C6), `reports/power_analysis.json` (C5)
**Depends on:** contracts only. Build against your own fixtures.

## 1. Goal
Build an interactive Streamlit dashboard that a PM or finance lead could use to understand the experiment in two minutes and explore segments on their own. Also export tidy CSVs so the same dashboard can be rebuilt in Power BI (a skill on the resume).

## 2. Non-goals
No statistics computed in the app, except simple descriptive filtering of the marts. All inferential numbers (CIs, p-values, decisions) come from `results.json`. Never read `config/ground_truth.yaml`.

## 3. Requirements

### 3.1 Pages (`app/Home.py` + `app/pages/`)
1. **Overview:** a decision banner (ship / ship segmented / don't ship, plus the rationale) from `results.json`. KPI tiles for recovery rate by variant, abs lift with CI, annualized revenue impact, and SRM status. A lift chart with CI (raw vs. CUPED).
2. **Segments:** a forest plot of segment lifts with BH-adjusted significance, a dimension selector, a sortable table, and a callout for segments recommended to ship.
3. **Guardrails:** a guardrail table with threshold and breach status, plus billing ticket and churn rates by variant.
4. **Explore:** filters (country, plan, funding, decline code) applied to `fct_experiment_invoices`, showing descriptive recovery rate by variant, the cumulative recovery-by-hour curve, and the retries distribution. Label it clearly: "Descriptive only. See Segments for significance."
5. **Methodology:** a summary of `power_analysis.json` (required n, MDE, power curve) and a link to `docs/experiment_design.md`.

### 3.2 Implementation
- Plotly charts. Colors match D: control `#8A8F98`, treatment `#3366CC`.
- Data access goes through `app/data.py`, with `@st.cache_data` loaders, a read-only DuckDB connection, and paths from `PROJECT_ROOT`.
- If an input file is missing, show a friendly `st.warning` that names the `make` target to run. Never crash.
- Launch: `streamlit run app/Home.py`.

### 3.3 Power BI exports
`python -m app.export --out exports/powerbi/` writes:
`experiment_invoices.csv` (from the fact table), `summary.csv`, `segments.csv` (results.json segments flattened), `guardrails.csv`, plus `exports/powerbi/README.md` listing the suggested visuals and the DAX measures for recovery rate and lift.

### 3.4 Fixtures & tests
- `tests/app/fixtures/`: a small DuckDB and a `results.json` that match the contracts, including one breached-guardrail variant and one SRM-failed variant.
- Tests use `streamlit.testing.v1.AppTest` to run each page against the fixtures and check there are no exceptions and the key elements are there (the decision banner text, the KPI count).
- A missing-input test: no DB and no results → warnings, no exception.

## 4. Acceptance criteria
- [ ] All five pages render against the fixtures with no exceptions (AppTest).
- [ ] The decision banner shows the correct text for each of the three decision values.
- [ ] Missing inputs show warnings, not exceptions.
- [ ] The CSV exports exist, have headers, and their row counts match the sources.
- [ ] `pytest tests/app` and `ruff check app tests/app` pass.

## 5. Handoff
`HANDOFF-E.md`: the launch command, screenshots of each page taken against the fixtures (`app/screenshots/*.png`), and the Power BI rebuild notes.
