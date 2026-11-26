# HANDOFF-A — Data simulation

## What was built
- `src/retrylab/sim/` — `schemas.py` (pyarrow schemas for the six C3 tables), `config.py`
  (loads `sim.yaml` + `ground_truth.yaml`), `generator.py` (the generative model), `__main__.py` (CLI).
- `config/sim.yaml`, `config/ground_truth.yaml` as specified in PRD-A, plus `config/sim.ci.yaml`
  (identical but `n_customers: 5000`) for PRD-F's CI job.
- `tests/sim/` — schemas, determinism (sha256 of every file), C3 invariants, control/treatment
  schedules, SRM toggle, and statistical checks on the full 50k run (marked `slow`).

## How to run
```bash
python -m retrylab.sim --config config/sim.yaml --out data/raw   # ~2s for 50k customers
pytest tests/sim                     # ~20s including slow tests
pytest tests/sim -m "not slow"       # ~4s, 2,000-customer run only
```
Python API: `retrylab.sim.generate(config_path, out_dir) -> dict[str, int]` (row counts) and
`retrylab.sim.simulate(cfg) -> dict[str, pyarrow.Table]`. Relative CLI paths resolve from
`PROJECT_ROOT` (falls back to cwd).

## Actual output (default config, seed 20260301)
| table | rows |
|---|---|
| raw_customers | 50,000 |
| raw_assignments | 50,000 |
| raw_invoices | 650,000 (600,000 pre-period + 50,000 experiment) |
| raw_payment_attempts | 889,482 |
| raw_support_tickets | 9,100 (1,554 billing_complaint, 7,546 other) |
| raw_subscription_events | 22,845 (22,278 involuntary, 567 voluntary) |

Observed vs. configured recovery:

| decline code | control (cfg) | treatment | observed lift (cfg) |
|---|---|---|---|
| insufficient_funds | 0.452 (0.45) | 0.520 | +0.068 (0.06 + 0.02 × 60% payday-known ≈ 0.072) |
| expired_card | 0.144 (0.15) | 0.150 | +0.006 (0.00) |
| do_not_honor | 0.302 (0.30) | 0.302 | +0.000 (0.01) |
| generic_decline | 0.357 (0.35) | 0.369 | +0.012 (0.02) |

Split 50.03% / 49.97%. Pre-period initial failure rate 6.3%. corr(`pre_failed_attempt_rate`,
`is_recovered`) = −0.285.

## Model notes
- A latent `stability ~ N(0,1)` lowers pre-period failure (logit) and raises experiment recovery
  (logit coef 1.8). Recovery is centred per (decline code × variant [× payday-known for
  insufficient_funds]) cell by bisection, so each cell's expected rate equals the configured rate.
- Treatment schedule: if the payday is known and a payday date falls inside the 7-day window, one
  retry lands on that date at the customer's modal pre-period success hour; the remaining retries
  are spread evenly over the window at that hour. Treatment also has an earlier success-retry
  distribution (mean retry index lower than control).
- Billing tickets sampled once per customer at the variant rate within 14 days; background `other`
  tickets at 0.15/customer over 2025-03-01..2026-05-01. Involuntary churn happens 7–30 days after
  failure (after the retry window); voluntary churn is never combined with involuntary.
- `inject_srm: true` drops exactly 3% of treatment customers (all their rows) after everything
  else is drawn, so the rest of the dataset is identical.

## Open issues / contract flags
1. **Signup rule vs. "no expired_card for recent signups".** C3 requires `signup_at` before
   2025-03-01, so every customer has ≥12 months of tenure at the experiment and has all 12
   pre-period invoices. The "no `expired_card` for customers who signed up in the last 6 months"
   rule is implemented but can never trigger, and no customer has a short pre-period history.
   If we want those cases, C3 needs to allow signups inside the pre-period.
2. **SRM detectability.** With 50k customers, a 3% treatment drop gives chi² ≈ 11 (p ≈ 0.001),
   right at the C6 threshold of 0.001, so it may or may not be flagged. The SRM failure test uses
   200k customers. Consider a 5% drop or a looser threshold if D needs to demonstrate detection
   at 50k.
3. **`.gitignore` from bootstrap ignores `HANDOFF-*.md`**, which conflicts with ground rule 7.
   This file was force-added; F may want to drop that ignore line.
4. Dependencies: needs `scipy` in dev for the SRM test (already in pyproject's main deps).
