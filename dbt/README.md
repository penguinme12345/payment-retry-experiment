# RetryLab dbt metrics layer

Turns the simulator's raw Parquet tables (contract C3) into tested DuckDB marts (C4) and a
MetricFlow semantic layer, so every experiment metric has one governed definition.

```bash
# from the repo root; PROJECT_ROOT defaults to "." when unset
export PROJECT_ROOT=$PWD
dbt build --project-dir dbt --profiles-dir dbt                    # real data in data/raw/
dbt build --project-dir dbt --profiles-dir dbt \
  --vars '{raw_dir: tests/dbt/fixtures/raw}'                      # hand-built fixtures
pytest tests/dbt                                                  # builds fixtures into a temp dir
cd dbt && DBT_PROFILES_DIR=. mf validate-configs                  # needs `pip install -e ".[semantic]"`
cd dbt && DBT_PROFILES_DIR=. mf query --metrics recovery_rate --group-by invoice__variant
```

Output: `data/warehouse.duckdb`, schema `main`. A 50k-customer build takes about 8 seconds.

## Lineage

```
sources (data/raw/*.parquet, read in place)
  raw_customers ──────────▶ stg_customers ───────────┬──────────────────────────────┐
  raw_assignments ────────▶ stg_assignments ─────────┤                              │
  raw_invoices ───────────▶ stg_invoices ────────────┼─▶ int_customer_pre_period ──┤
  raw_payment_attempts ───▶ stg_payment_attempts ────┼─▶ int_invoice_attempts ─────┤
  raw_support_tickets ────▶ stg_support_tickets ─────┼─▶ int_invoice_outcomes ─────┤
  raw_subscription_events ▶ stg_subscription_events ─┘                              ▼
                                                                    fct_experiment_invoices
                                                                      │        │        │
                                                   agg_experiment_summary      │   semantic model
                                                         agg_experiment_segments  experiment_invoices
                                                                                    + metrics
  metricflow_time_spine (2025-01-01 .. 2026-12-31, daily)
```

| Layer | Models | Materialization |
|---|---|---|
| staging | `stg_*` (rename and cast only) | view |
| intermediate | `int_invoice_attempts`, `int_customer_pre_period`, `int_invoice_outcomes` | view |
| marts | `fct_experiment_invoices`, `agg_experiment_summary`, `agg_experiment_segments` | table |
| utilities | `metricflow_time_spine` | table |
| semantic | `experiment_invoices` semantic model, metrics | MetricFlow YAML |

`fct_experiment_invoices` has an enforced dbt model contract, so a column name or type drift
fails the build.

## Window rules (dbt vars)

| var | default | rule |
|---|---|---|
| `recovery_window_days` | 7 | recovered if a retry succeeds in `(failed_at, failed_at + 7d]` |
| `ticket_window_days` | 14 | billing_complaint ticket in `[failed_at, failed_at + 14d]` |
| `churn_window_days` | 30 | churned_involuntary event in `[failed_at, failed_at + 30d]` |
| `pre_period_start` / `pre_period_end` | 2025-03-01 / 2026-02-28 | invoice `created_at` in `[start 00:00, end + 1 day)`, experiment invoices excluded |
| `experiment_start` / `experiment_end` | 2026-03-01 / 2026-03-31 | checked by a singular test |
| `raw_dir` | `data/raw` | relative to `PROJECT_ROOT`, or absolute |

`failed_at` is the timestamp of attempt 0. All upper bounds are inclusive, so a payment at
exactly +7d 00:00:00 counts and one at +7d 00:00:01 does not.

## Metric dictionary

All rates use the number of experiment invoices as the denominator. One customer contributes
exactly one invoice.

| Metric | Type | Definition | Numerator / denominator | Window |
|---|---|---|---|---|
| `experiment_invoices` | simple (count) | Failed invoices enrolled in `retry_timing_v1` | count of invoices | invoice failed 2026-03-01..03-31 |
| `recovered_revenue` | simple (sum) | USD collected by retries | sum of `recovered_amount_usd` | 7 days |
| `recovery_rate` | ratio | **Primary.** Share of failed invoices recovered by a retry | `recovered_invoices` / `experiment_invoices` | 7 days |
| `recovered_revenue_per_invoice` | ratio | Average USD recovered per failed invoice, unrecovered = $0 | `recovered_revenue` / `experiment_invoices` | 7 days |
| `avg_retries_per_invoice` | ratio | Retry charges per failed invoice (initial charge excluded, max 4) | `retries_attempted_total` / `experiment_invoices` | retry schedule |
| `billing_ticket_rate` | ratio | **Guardrail.** Share whose customer filed a billing complaint | `billing_ticket_invoices` / `experiment_invoices` | 14 days |
| `involuntary_churn_rate` | ratio | **Guardrail.** Share whose customer churned involuntarily | `involuntary_churn_invoices` / `experiment_invoices` | 30 days |

The four helper metrics (`recovered_invoices`, `retries_attempted_total`,
`billing_ticket_invoices`, `involuntary_churn_invoices`) are the ratio numerators. MetricFlow
requires ratio inputs to be metrics.

Dimensions: `variant`, `country`, `plan_tier`, `card_funding`, `initial_decline_code`,
`is_recovered`, and `failed_at` (day grain). Group by them as `invoice__<name>`.

## Tests

- Generic: `unique` + `not_null` on every key, `accepted_values` on variant, decline codes,
  segment values and dimensions, `relationships` from staging and the fact to `stg_customers`,
  and a custom `unique_combination` on the segments grain.
- Singular (`dbt/tests/`): one experiment invoice per customer, `recovered_amount_usd = 0` when
  not recovered, `retries_attempted <= 4`, summary and segment totals reconcile to the fact,
  exactly one assignment per customer, and every experiment invoice failed inside the window.
- `tests/dbt/`: 20 hand-built customers, one edge case each (see `build_fixtures.py`), checked
  against `tests/dbt/expected/*.csv` exactly, plus contract schema and semantic manifest checks.
