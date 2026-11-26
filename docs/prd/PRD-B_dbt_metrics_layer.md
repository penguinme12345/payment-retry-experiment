# PRD-B — dbt Metrics Layer

**Owner paths:** `dbt/`, `tests/dbt/`
**Consumes:** `data/raw/*.parquet` (C3) · **Produces:** DuckDB marts + semantic layer (C4)
**Depends on:** contracts only. Build against your own fixture Parquet files.

## 1. Goal
Turn the raw tables into tested, documented marts and a **MetricFlow semantic layer**, so every metric in the project has a single governed definition. This is the "extend a metrics semantic layer" part of the posting, so the YAML should look production-grade.

## 2. Non-goals
No statistical testing (D) and no dashboards (E).

## 3. Requirements

### 3.1 Project setup
- `dbt/dbt_project.yml` (project name `retrylab`) and `dbt/profiles.yml` with a `dbt-duckdb` target:
  `path: "{{ env_var('PROJECT_ROOT', '.') }}/data/warehouse.duckdb"`, schema `main`.
- Invocation, always from the repo root: `dbt build --project-dir dbt --profiles-dir dbt`
- Sources in `dbt/models/staging/_sources.yml` reading Parquet via `meta.external_location: "{{ env_var('PROJECT_ROOT', '.') }}/data/raw/{name}.parquet"`.
- A var `raw_dir`, overridable so tests can point at fixtures: `--vars '{raw_dir: tests/dbt/fixtures/raw}'`.

### 3.2 Layers
| Layer | Models | Materialization |
|---|---|---|
| staging | `stg_customers`, `stg_assignments`, `stg_invoices`, `stg_payment_attempts`, `stg_support_tickets`, `stg_subscription_events` (rename/cast only) | view |
| intermediate | `int_invoice_attempts` (per-invoice attempt rollup), `int_customer_pre_period` (CUPED covariates), `int_invoice_outcomes` (tickets/churn windows) | view |
| marts | `fct_experiment_invoices`, `agg_experiment_summary`, `agg_experiment_segments` | table |
| utility | `metricflow_time_spine` (daily, 2025-01-01 to 2026-12-31) | table |

Column names, types, and definitions in the marts must match C4 exactly. Define the observation windows (7/14/30 days) and the pre-period dates as dbt vars, not hard-coded literals.

### 3.3 Tests (in YAML)
- `unique` + `not_null` on all primary keys. `accepted_values` on variant, decline codes, and segment dimensions. `relationships` from facts to customers.
- Singular tests in `dbt/tests/`: (a) one experiment invoice per customer, (b) `recovered_amount_usd = 0` when not recovered, (c) `retries_attempted ≤ 4`, (d) `agg_experiment_summary` totals reconcile to `fct_experiment_invoices`, (e) every customer has exactly one assignment.

### 3.4 Semantic layer
In `dbt/models/semantic/`:
- A `semantic_model` on `fct_experiment_invoices` with entity `invoice` (primary) and `customer` (foreign), a time dimension `failed_at` (day grain), categorical dimensions `variant`, `country`, `plan_tier`, `card_funding`, `initial_decline_code`, and the measures needed below.
- Metrics (names fixed by C4): `experiment_invoices` (simple count), `recovered_revenue` (simple sum), `recovery_rate` (ratio), `recovered_revenue_per_invoice` (ratio), `avg_retries_per_invoice` (ratio), `billing_ticket_rate` (ratio), `involuntary_churn_rate` (ratio).
- Every metric gets a `description` written for a business reader (what it means, the numerator/denominator, the window).

### 3.5 Documentation
- A description on every model and mart column.
- `dbt/README.md`: a lineage overview and a "metric dictionary" table.

### 3.6 Fixtures
`tests/dbt/fixtures/raw/*.parquet`: about 20 hand-built customers that cover each edge case (recovered on retry 4, recovered on day 8 = not recovered, ticket on day 15 = excluded, no pre-period history, prepaid + insufficient_funds, and so on). Write the expected mart values for those customers in `tests/dbt/expected/*.csv`.

## 4. Acceptance criteria
- [ ] `dbt build` passes on the fixtures with zero test failures.
- [ ] `dbt parse` validates the semantic manifest with no errors (if `dbt-metricflow` is installed, `mf validate-configs` passes too).
- [ ] `pytest tests/dbt` runs dbt on the fixtures and checks the marts against `expected/*.csv` exactly.
- [ ] Mart schemas match C4 (column names and DuckDB types checked in a test).
- [ ] Every edge case listed in 3.6 has a fixture row and a passing assertion.

## 5. Handoff
`HANDOFF-B.md`: commands, lineage, the metric dictionary, and any assumptions you made about window boundaries (inclusive/exclusive).
