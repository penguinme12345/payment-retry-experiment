# PRD-A — Data Simulation

**Owner paths:** `src/retrylab/sim/`, `config/sim.yaml`, `config/ground_truth.yaml`, `tests/sim/`
**Produces:** `data/raw/*.parquet` (contract C3)
**Depends on:** contracts only

## 1. Goal
Generate a realistic, deterministic synthetic dataset for a subscription business. It covers customer history, one failed invoice per customer in March 2026, retry attempts under each variant's policy, support tickets, and churn events. A known treatment effect is planted so the downstream pipeline can be checked against it.

## 2. Non-goals
- No dbt models, statistics, or dashboards.
- No real Stripe data or APIs.

## 3. Requirements

### 3.1 Config
`config/sim.yaml` (tunable, committed):
```yaml
seed: 20260301
n_customers: 50000
country_mix:   {US: 0.40, CA: 0.08, GB: 0.12, DE: 0.10, FR: 0.08, BR: 0.08, IN: 0.08, AU: 0.06}
plan_mix:      {basic: 0.55, pro: 0.35, business: 0.10}
funding_mix:   {credit: 0.55, debit: 0.38, prepaid: 0.07}
brand_mix:     {visa: 0.55, mastercard: 0.35, amex: 0.10}
decline_mix:   {insufficient_funds: 0.45, expired_card: 0.20, do_not_honor: 0.20, generic_decline: 0.15}
payday_known_rate: 0.6
pre_period_months: 12
inject_srm: false           # if true, drop 3% of treatment customers to test SRM detection
```

`config/ground_truth.yaml` (true effects; see C7):
```yaml
baseline_recovery:   {insufficient_funds: 0.45, expired_card: 0.15, do_not_honor: 0.30, generic_decline: 0.35}
treatment_lift_abs:  {insufficient_funds: 0.06, expired_card: 0.00, do_not_honor: 0.01, generic_decline: 0.02}
payday_known_extra_lift_abs: 0.02     # extra lift, applied only to insufficient_funds when payday is known
billing_ticket_rate: {control: 0.030, treatment: 0.031}
involuntary_churn_given_unrecovered: 0.70
voluntary_churn_30d: 0.02
```

### 3.2 Generative model
1. **Customers:** sample attributes from the mixes. Draw a latent `stability ~ Normal(0, 1)` per customer. It must raise the probability of paying on time in the pre-period **and** the probability of recovery, so the CUPED covariate is genuinely predictive (target correlation between `pre_failed_attempt_rate` and `is_recovered` of about −0.25 to −0.35).
2. **Pre-period:** create one monthly invoice per customer for each month after their signup, within the pre-period (up to 12). Each has an initial attempt that fails with a probability depending on stability (≈3–10%), with retries under the control policy. Most end up paid.
3. **Experiment invoice:** one per customer, `created_at` uniform over the March 2026 window, attempt 0 fails with a decline code from `decline_mix`. Prepaid cards skew toward `insufficient_funds`, and there's no `expired_card` on customers who signed up in the last 6 months.
4. **Assignment:** 50/50 Bernoulli per customer with the seed. `assigned_at` = the attempt 0 timestamp.
5. **Recovery:** P(recovered) = baseline[decline] + (treatment ? lift[decline] (+ payday extra) : 0), adjusted by stability on the logit scale, with the adjustment centered so the population average matches the configured rates within ±0.5pp. If recovered, pick which retry (1–4) succeeds. Treatment recovers earlier on average.
6. **Retry timestamps:** control at +1/+3/+5/+7 days, same hour. Treatment: if payday is known and falls in the 7-day window, schedule a retry within 24h after payday. Otherwise use the customer's modal pre-period success hour. Never more than 4 retries or past 7 days.
7. **Tickets & churn:** sample billing tickets at the variant rate within 14 days, plus background `other` tickets. Involuntary churn within 30 days for unrecovered invoices at the configured rate. Background voluntary churn for everyone.
8. **SRM toggle:** if `inject_srm`, drop 3% of treatment customers *after* assignment.

### 3.3 Interface
- CLI: `python -m retrylab.sim --config config/sim.yaml --out data/raw`
- Function: `generate(config_path: Path, out_dir: Path) -> dict[str, int]` returns row counts per table.
- Writes the six Parquet files from C3 with exactly those column names and types (use pyarrow schemas defined in `src/retrylab/sim/schemas.py`).
- Runtime under 60 seconds for 50k customers on a laptop.

## 4. Acceptance criteria
- [ ] All six tables exist, schemas match C3 exactly (checked by a test against `schemas.py`).
- [ ] Two runs with the same seed give identical files (compare hashes).
- [ ] C3 invariants hold: one experiment invoice per customer, attempt 0 failed, no attempts after a success, `status='paid'` ⇔ a succeeded attempt, ≤4 retries, all retries within 7 days.
- [ ] Observed control recovery per decline code is within ±1.5pp of `baseline_recovery`. Observed treatment − control lift per decline code is within ±2pp of the configured lift.
- [ ] Assignment split is within 49–51%, and an SRM chi-square test passes with `inject_srm: false` and fails with `true`.
- [ ] Correlation between `pre_failed_attempt_rate` and recovery is in [−0.35, −0.20].
- [ ] `ruff check src/retrylab/sim tests/sim` is clean, and `pytest tests/sim` passes (use `n_customers: 2000` in tests for speed).

## 5. Handoff
`HANDOFF-A.md`: how to run it, actual row counts, observed vs. configured rates, and any deviations from the contract.
