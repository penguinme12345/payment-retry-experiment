# RetryLab — Shared Contracts

**This file is the single source of truth for every interface between workstreams.** Don't change it unilaterally. Propose changes in a `HANDOFF-<letter>.md` file.

All timestamps are UTC, stored as `TIMESTAMP` (Parquet `timestamp[us]`) with no timezone. Money is `DOUBLE` in USD, rounded to 2 decimals. IDs are strings.

---

## C1. Repo layout & paths

```
retrylab/
├── config/              sim.yaml, ground_truth.yaml               (A)
├── data/raw/            *.parquet raw tables                       (written by A)
├── data/warehouse.duckdb  dbt target database                      (written by B)
├── dbt/                 dbt project + profiles.yml                 (B)
├── src/retrylab/
│   ├── sim/             data generator                             (A)
│   ├── design/          power analysis                             (C)
│   ├── analysis/        statistical analysis                       (D)
│   └── reporting/       memo rendering                             (F)
├── app/                 Streamlit dashboard                        (E)
├── exports/powerbi/     CSV exports                                (E)
├── reports/             power_analysis.json (C), results.json (D), figures/ (D)
├── docs/                experiment_design.md (C), memo.md (F), prd/
└── tests/{sim,dbt,design,analysis,app,integration}/
```

The environment variable **`PROJECT_ROOT`** is the repo's absolute path. Every tool resolves paths from it. If it isn't set, code falls back to `Path.cwd()`.

## C2. Experiment constants

| Constant | Value |
|---|---|
| `experiment_id` | `"retry_timing_v1"` |
| Variants | `"control"`, `"treatment"` |
| Allocation | 50/50, randomized at the **customer** level |
| Experiment window (failed invoices created) | `2026-03-01 00:00:00` to `2026-03-31 23:59:59` |
| Pre-period (historical invoices) | `2025-03-01` to `2026-02-28` |
| Retry window | up to **4 retries** within **7 days** of the initial failure |
| Control schedule | retries at +1, +3, +5, +7 days after the initial failure, same hour-of-day |
| Treatment schedule | same max 4 retries within 7 days, timed by the "smart" policy (payday-aware, customer's historical success hour) |
| Churn observation | 30 days after the initial failure |
| Ticket observation | 14 days after the initial failure |
| Target sample | 50,000 customers, each with exactly **one** failed invoice in the experiment window |
| Default seed | `20260301` |

**Decline codes** (initial failure): `insufficient_funds`, `expired_card`, `do_not_honor`, `generic_decline`

**Segment dimensions:** `country` ∈ {US, CA, GB, DE, FR, BR, IN, AU} · `plan_tier` ∈ {basic, pro, business} · `card_funding` ∈ {credit, debit, prepaid} · `initial_decline_code` (above)

## C3. Raw tables — `data/raw/<table>.parquet` (producer: A)

### `raw_customers` — one row per customer
| column | type | notes |
|---|---|---|
| customer_id | string | `cus_` + 6-digit zero-padded, e.g. `cus_000001` |
| signup_at | timestamp | before 2025-03-01 |
| country | string | segment values from C2 |
| plan_tier | string | basic / pro / business |
| monthly_price_usd | double | basic 9.00, pro 29.00, business 99.00 |
| card_brand | string | visa / mastercard / amex |
| card_funding | string | credit / debit / prepaid |
| payday_day_of_month | int, nullable | 1, 15, or 28; null if unknown |

### `raw_assignments` — one row per customer
| column | type |
|---|---|
| customer_id | string |
| experiment_id | string (`retry_timing_v1`) |
| variant | string (control / treatment) |
| assigned_at | timestamp (= the initial failed attempt's `attempted_at`) |

### `raw_invoices` — historical + experiment invoices
| column | type | notes |
|---|---|---|
| invoice_id | string | `in_` + 7-digit zero-padded |
| customer_id | string | |
| amount_usd | double | = the customer's monthly_price_usd |
| created_at | timestamp | |
| is_experiment_invoice | boolean | true for the one failed invoice per customer in the window |
| status | string | `paid` or `uncollectible` (final state) |

### `raw_payment_attempts` — one row per charge attempt
| column | type | notes |
|---|---|---|
| attempt_id | string | `py_` + 8-digit zero-padded |
| invoice_id | string | |
| attempt_number | int | 0 = initial attempt, 1–4 = retries |
| attempted_at | timestamp | |
| outcome | string | `succeeded` or `failed` |
| decline_code | string, nullable | null when succeeded |

Invariants: every experiment invoice has a failed attempt 0. Attempts stop after the first success. An invoice is `paid` exactly when one of its attempts succeeded.

### `raw_support_tickets`
| column | type |
|---|---|
| ticket_id | string (`tkt_` + 7 digits) |
| customer_id | string |
| created_at | timestamp |
| category | string: `billing_complaint` or `other` |

### `raw_subscription_events`
| column | type |
|---|---|
| customer_id | string |
| event_type | string: `churned_involuntary` or `churned_voluntary` |
| event_at | timestamp |

## C4. Marts — DuckDB `data/warehouse.duckdb`, schema `main` (producer: B; consumers: D, E)

### `fct_experiment_invoices` — one row per experiment invoice (≈50,000)
| column | type | definition |
|---|---|---|
| invoice_id | varchar | |
| customer_id | varchar | |
| variant | varchar | from assignments |
| country, plan_tier, card_funding | varchar | from customers |
| initial_decline_code | varchar | decline_code of attempt 0 |
| amount_usd | double | |
| failed_at | timestamp | attempt 0 `attempted_at` |
| is_recovered | boolean | any retry succeeded within 7 days of failed_at |
| recovered_at | timestamp, nullable | |
| hours_to_recovery | double, nullable | |
| retries_attempted | integer | count of attempts with attempt_number ≥ 1 |
| recovered_amount_usd | double | amount_usd if recovered else 0 |
| had_billing_ticket_14d | boolean | billing_complaint within 14 days of failed_at |
| churned_involuntary_30d | boolean | churned_involuntary within 30 days of failed_at |
| pre_paid_invoice_count | integer | paid invoices in the pre-period (CUPED covariate) |
| pre_failed_attempt_rate | double | failed attempts / all attempts in the pre-period; 0 if none |

### `agg_experiment_summary` — one row per variant
`variant, n_invoices, n_recovered, recovery_rate, recovered_revenue_usd, recovered_revenue_per_invoice_usd, avg_retries_per_invoice, billing_ticket_rate, involuntary_churn_rate`

### `agg_experiment_segments` — one row per (variant, segment_dimension, segment_value)
`variant, segment_dimension, segment_value, n_invoices, n_recovered, recovery_rate, recovered_revenue_per_invoice_usd`
`segment_dimension` ∈ {`country`, `plan_tier`, `card_funding`, `initial_decline_code`}

### Semantic layer (dbt MetricFlow YAML, B)
These metric names are part of the contract: `recovery_rate`, `recovered_revenue`, `recovered_revenue_per_invoice`, `avg_retries_per_invoice`, `billing_ticket_rate`, `involuntary_churn_rate`, `experiment_invoices`.

## C5. `reports/power_analysis.json` (producer: C; consumers: D, E, F)

```json
{
  "experiment_id": "retry_timing_v1",
  "primary_metric": "recovery_rate",
  "baseline_rate": 0.345,
  "mde_abs": 0.02,
  "alpha": 0.05,
  "power": 0.8,
  "two_sided": true,
  "required_n_per_arm": 8983,
  "planned_n_per_arm": 25000,
  "achieved_power_at_mde": 0.997,
  "mde_curve": [{"n_per_arm": 5000, "mde_abs": 0.0266}],
  "guardrails": [
    {"metric": "billing_ticket_rate", "max_acceptable_increase_abs": 0.005},
    {"metric": "involuntary_churn_rate", "max_acceptable_increase_abs": 0.0}
  ]
}
```
The numbers above are illustrative. C computes the real ones; the keys and types are fixed.

## C6. `reports/results.json` (producer: D; consumers: E, F)

```json
{
  "experiment_id": "retry_timing_v1",
  "generated_at": "2026-04-15T12:00:00Z",
  "n_control": 25000, "n_treatment": 25000,
  "srm": {"chi2": 0.0, "p_value": 1.0, "passed": true, "threshold": 0.001},
  "primary": {
    "metric": "recovery_rate",
    "control": 0.345, "treatment": 0.377,
    "abs_lift": 0.032, "rel_lift": 0.093,
    "ci_low": 0.024, "ci_high": 0.040, "ci_level": 0.95,
    "p_value": 1e-12, "significant": true
  },
  "cuped": {
    "covariate": "pre_failed_attempt_rate",
    "abs_lift": 0.032, "ci_low": 0.026, "ci_high": 0.038,
    "variance_reduction_pct": 18.5
  },
  "secondary": [
    {"metric": "recovered_revenue_per_invoice_usd", "control": 0.0, "treatment": 0.0,
     "abs_lift": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p_value": 0.0}
  ],
  "guardrails": [
    {"metric": "billing_ticket_rate", "control": 0.0, "treatment": 0.0, "abs_lift": 0.0,
     "ci_low": 0.0, "ci_high": 0.0, "p_value": 0.0, "threshold_abs": 0.005, "breached": false}
  ],
  "segments": [
    {"dimension": "initial_decline_code", "value": "insufficient_funds",
     "n_control": 0, "n_treatment": 0, "control_rate": 0.0, "treatment_rate": 0.0,
     "abs_lift": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p_value": 0.0,
     "p_value_adj": 0.0, "significant_adj": false}
  ],
  "revenue_impact": {
    "annualized_incremental_revenue_usd": 0.0,
    "ship_scope": "all | segments",
    "ship_segments": [{"dimension": "initial_decline_code", "value": "insufficient_funds"}],
    "assumptions": ["Monthly failed-invoice volume equals the experiment window volume", "..."]
  },
  "recommendation": {"decision": "ship | ship_segmented | do_not_ship", "rationale": "one sentence"}
}
```
Values are illustrative. Keys, nesting, and types are fixed. `p_value_adj` uses Benjamini–Hochberg across all segment rows.

## C7. Ground truth (A only, used only for validation)

`config/ground_truth.yaml` holds the true simulated effects. **Analysis (D), the dashboard (E), and the memo (F) must never read it.** Only `tests/sim/` and `tests/integration/` may read it, to check that the pipeline recovers the planted effect.
