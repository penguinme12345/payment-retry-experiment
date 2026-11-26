# HANDOFF-B — dbt metrics layer

## What was built
- `dbt/` — project `retrylab` (dbt-core 1.9, dbt-duckdb): 6 staging views, 3 intermediate views,
  3 mart tables matching C4, `metricflow_time_spine`, a semantic model and 11 metrics (the 7
  contract metrics plus 4 numerator helpers), 6 singular tests, 1 custom generic test.
  `dbt/README.md` has the lineage and the metric dictionary.
- `tests/dbt/` — `build_fixtures.py` (20 hand-built edge-case customers → `fixtures/raw/*.parquet`
  and hand-written expectations → `expected/*.csv`) and `test_marts.py`.

## How to run
```bash
export PROJECT_ROOT=$PWD
dbt build --project-dir dbt --profiles-dir dbt          # 97 nodes, ~8s on 50k customers
pytest tests/dbt                                        # 30 tests, ~11s; builds into a tmp dir
pip install -e ".[semantic]"                            # optional, for mf
cd dbt && DBT_PROFILES_DIR=. mf validate-configs        # 0 errors, 0 warnings
```
`pytest tests/dbt` never touches `data/warehouse.duckdb`: it sets `PROJECT_ROOT` to a temp dir
and passes the absolute fixture path as `raw_dir`.

## Verified on the real simulator output (seed 20260301, 50k customers)
`dbt build` PASS=97. Recovery by decline code matches HANDOFF-A to 3 dp (insufficient_funds
0.452 → 0.520, expired_card 0.144 → 0.150, do_not_honor 0.302 → 0.302, generic_decline
0.357 → 0.369). Overall recovery 0.3485 (control) vs 0.3812 (treatment);
corr(pre_failed_attempt_rate, is_recovered) = −0.285, as HANDOFF-A reports.
`mf query --metrics recovery_rate --group-by invoice__variant` returns the same numbers.

## Window boundaries (assumptions)
- `failed_at` = attempt 0 `attempted_at`. Every window is measured from it.
- Recovery: first succeeded retry (attempt_number ≥ 1) with `attempted_at <= failed_at + 7d`.
  Exactly +7d counts; +7d 1s does not. A later success leaves `is_recovered = false`,
  `recovered_at`/`hours_to_recovery` null and `recovered_amount_usd = 0`, even though the raw
  invoice status is `paid`.
- Tickets and churn: `[failed_at, failed_at + N days]`, both ends inclusive. Tickets before the
  failure, `other` tickets and voluntary churn are excluded.
- Pre-period: non-experiment invoices with `created_at` in `[2025-03-01 00:00, 2026-03-01 00:00)`.
  `pre_failed_attempt_rate` counts all attempts on those invoices (by invoice, not by attempt
  time). Customers with no history get 0 and 0.0.
- `retries_attempted` counts all retries, not only those inside the 7-day window.
- `recovered_revenue_usd` in the summary is rounded to cents; the other rates are unrounded.

## Open issues / contract flags
1. **Types for the agg tables aren't in C4.** I used INTEGER for counts and DOUBLE for rates and
   money; `tests/dbt/test_marts.py` pins those. D and E should read them as such.
2. **`dbt-metricflow` and the dbt pin.** The latest `dbt-metricflow` pulls dbt-core 1.12, which
   breaks pyproject's `dbt-core<1.10`. Installing with the pins in place resolves to
   dbt-metricflow 0.8.2, which works. F may want `semantic = ["dbt-metricflow>=0.7,<0.9"]`.
3. **MetricFlow group-by names** are `invoice__variant` etc. (entity prefix), not
   `experiment_invoices__variant`.
4. Ratio metrics need their numerators as metrics, so there are 4 extra helper metrics beyond
   the 7 contract names. Nothing was renamed.
5. `.gitignore` ignores `HANDOFF-*.md` (same as HANDOFF-A #3); this file was force-added.
