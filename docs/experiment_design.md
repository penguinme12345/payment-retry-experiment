# Pre-registration: smart retry timing (`retry_timing_v1`)

**Status:** final, locked before any experiment results were computed.
**Primary metric:** `recovery_rate` · **Design numbers:** `reports/power_analysis.json`
(regenerate with `python -m retrylab.design`).

## 1. Background

When a subscription renewal charge fails, the customer has not chosen to leave, but if we never
collect they churn anyway. This *involuntary churn* is pure lost revenue: the customer still wants
the product. Today every failed invoice gets up to four retries on a fixed schedule (day 1, 3, 5
and 7 after the failure, at the same hour as the original charge).

"Smart retries" keep the same budget (at most four retries within seven days) but choose *when*
to retry: just after the customer's known payday, and at the hour of day when their past charges
have tended to succeed. The bet is that a retry that lands when money is in the account succeeds
more often, mainly for `insufficient_funds` declines. Retrying at a better time costs nothing, so
any real lift is close to free revenue.

## 2. Hypothesis

Let p_C and p_T be the share of experiment invoices recovered within seven days of the initial
failure under the fixed schedule (control) and the smart schedule (treatment).

- **H0:** p_T = p_C.
- **H1:** p_T ≠ p_C (two-sided, α = 0.05).

We expect p_T > p_C. The test is two-sided so that a harmful policy is detected with the same
rigour as a helpful one. We size the test to detect an absolute lift of **2.0pp** from a baseline
of **34.5%** with 80% power.

## 3. Unit of randomization and analysis

- **Randomization:** customer, 50/50, at the moment of their first failed invoice in the window.
  Randomizing customers rather than invoices means a customer always sees one retry policy, so
  their experience and any support contact can be attributed to a single arm.
- **Analysis:** invoice. Each customer contributes exactly one failed invoice during the window,
  so the unit of analysis and the unit of randomization are 1:1. Observations are therefore
  independent across customers, and no cluster-robust standard errors or design-effect
  correction are needed. If a later version allows several invoices per customer, the analysis
  must switch to customer-clustered standard errors.

## 4. Metrics

Every metric is defined once in the dbt semantic layer (contract C4) and read from there.

| Role | Metric (dbt name) | Definition |
|---|---|---|
| Primary | `recovery_rate` | recovered experiment invoices / experiment invoices (any retry succeeded within seven days) |
| Secondary | `recovered_revenue_per_invoice` | recovered USD / experiment invoices (built on `recovered_revenue`) |
| Secondary | time to recovery | `hours_to_recovery` among recovered invoices, from `fct_experiment_invoices` |
| Diagnostic | `avg_retries_per_invoice` | retries used per invoice; smart retries should not need more |
| Guardrail | `billing_ticket_rate` | share of invoices with a billing complaint within 14 days; maximum acceptable increase **+0.5pp** |
| Guardrail | `involuntary_churn_rate` | share of customers who churn involuntarily within 30 days; **no increase** allowed (threshold 0.0pp) |

The guardrail thresholds are the `guardrails` block of `power_analysis.json`. The sample-size
count comes from `experiment_invoices`.

## 5. Sample size and duration

Two-proportion z-test, baseline **34.5%**, MDE **2.0pp**, α = 0.05 two-sided, power 80%.

The baseline is the historical recovery rate under the fixed schedule, blended by the historical
decline mix (45% insufficient funds at 45.0% recovery, 20% expired card at 15.0%, 20% do not
honor at 30.0%, 15% generic decline at 35.0%).

| | Value |
|---|---|
| Required n per arm for the overall effect | **8,985** |
| Planned n per arm | **25,000** |
| Power to detect 2.0pp at the planned n | **99.7%** |
| MDE at the planned n (80% power) | **1.20pp** |

**MDE by sample size (overall effect):**

| n per arm | 2,500 | 5,000 | 10,000 | 15,000 | 20,000 | 25,000 |
|---|---|---|---|---|---|---|
| MDE | 3.81pp | 2.69pp | 1.90pp | 1.55pp | 1.34pp | 1.20pp |

**Why 25,000 per arm instead of 8,985.** The overall effect alone needs only 8,985 invoices per
arm. But the ship decision may be segmented (section 7), and the effect is expected to sit
mostly in `insufficient_funds`. At 25,000 per arm the main segments are themselves powered for
roughly the overall target:

| Segment | n per arm | Segment baseline | MDE (80% power) |
|---|---|---|---|
| `insufficient_funds` | 11,250 | 45.0% | 1.86pp |
| `expired_card` | 5,000 | 15.0% | 2.06pp |
| `do_not_honor` | 5,000 | 30.0% | 2.60pp |
| `generic_decline` | 3,750 | 35.0% | 3.12pp |
| plan `basic` | 13,750 | 34.5% | 1.61pp |
| card `debit` | 9,500 | 34.5% | 1.94pp |
| country `US` | 10,000 | 34.5% | 1.90pp |

Small segments (for example `prepaid` cards at 1,750 per arm, MDE 4.57pp, or `AU` at 1,500 per
arm, MDE 4.94pp) are read as exploratory only. Per-segment MDEs are nominal (before the
Benjamini–Hochberg adjustment); the full list is `segment_mde` in `power_analysis.json`.

**Duration.** All customers whose first failed invoice falls between 2026-03-01 and 2026-03-31
are enrolled (about 50,000, so 25,000 per arm). Each invoice is followed for seven days of
retries, 14 days for tickets and 30 days for churn, so the readout is fixed at 30 days after the
last enrollment. There are no interim looks.

## 6. Analysis plan

1. **Validity first: sample ratio mismatch (SRM).** χ² goodness-of-fit of the arm counts against
   50/50. If p < 0.001 the experiment is invalid and no other result is interpreted.
2. **Primary test.** Two-proportion z-test on `recovery_rate`, with a 95% confidence interval for
   p_T − p_C (Newcombe hybrid score interval; Wald reported alongside as a check). Report the
   absolute lift (pp) and the relative lift.
3. **Variance reduction (CUPED).** Re-estimate the lift with the pre-period covariate
   `pre_failed_attempt_rate` (θ estimated on pooled data). CUPED tightens the interval; it is a
   precision improvement, not a separate hypothesis, and the decision uses the primary test.
4. **Secondary metrics.** Welch t-test and CI on `recovered_revenue_per_invoice`; time to
   recovery is described (medians, cumulative recovery curve by day) rather than tested.
5. **Guardrails.** Lift and 95% CI for `billing_ticket_rate` and `involuntary_churn_rate`. A
   guardrail is *breached* when the lower bound of its CI is above the threshold, i.e. we are
   confident treatment is worse by more than the allowed amount.
6. **Pre-declared segments.** Every value of `initial_decline_code`, `plan_tier`,
   `card_funding` and `country` (18 segments). Each gets its own lift, CI and p-value, and
   p-values are adjusted across all 18 with Benjamini–Hochberg at a 5% false discovery rate.
   No segments are added after the data is seen.

## 7. Decision rules

Applied in order; the first rule that fires decides.

1. **If SRM fails** (p < 0.001): **don't ship**. The experiment is invalid; fix assignment and
   rerun.
2. **If any guardrail is breached**: **don't ship**, even if recovery improved. Investigate the
   mechanism (e.g. retries landing at bad times trigger complaints) before re-testing.
3. **If the overall lift is positive and significant** (p < 0.05) **and no segment is
   significantly negative** after BH: **ship to everyone**.
4. **Else, if one or more segments are significantly positive after BH**: **ship segmented**,
   to those segments only, keeping the fixed schedule elsewhere.
5. **Otherwise**: **don't ship**. The policy is not worth its complexity.

A significantly *negative* overall lift is covered by rule 5 and also triggers a review of the
policy logic.

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Peeking** inflates false positives | Fixed horizon, one readout 30 days after the last enrollment, no early stopping. |
| **Novelty effects** | Customers don't see retry timing, so novelty is unlikely; we still compare the lift in the first and second half of the window as a check. |
| **Card-network retry limits** | Both arms keep the same budget (four retries in seven days), so neither breaks network rules; treatment only moves retries in time. |
| **Interference** between arms | None expected: one customer's retry timing doesn't affect another's card. |
| **Multiple comparisons** across segments | Pre-declared list of 18 segments plus Benjamini–Hochberg. |
| **Simulated data** | This experiment runs on synthetic data from `retrylab.sim`. The effect sizes are planted, so the results show the method, not a real-world estimate. |

## 9. Pre-registration statement

This document, including the hypotheses, metrics, sample size, analysis plan and decision rules,
was finalized before any experiment results were computed. The numbers in it are generated from
design assumptions only (`retrylab.design`) and never from the experiment data or from the
simulator's ground truth. Any later deviation from this plan will be reported as such.

---

## Appendix: power math

For baseline p₁, MDE δ, and p₂ = p₁ + δ, with p̄ = (p₁ + p₂)/2, the per-arm sample size for a
two-sided two-proportion z-test is

```
n = ( z_{1−α/2} · √(2 p̄ (1 − p̄)) + z_{1−β} · √(p₁(1 − p₁) + p₂(1 − p₂)) )² / δ²
```

rounded up (pooled variance under H0, unpooled under H1, no continuity correction). The MDE for
a given n is found by solving this equation for δ numerically (Brent's method), and achieved
power is

```
power = Φ( (δ − z_{1−α/2} · √(2 p̄ q̄ / n)) / √((p₁q₁ + p₂q₂) / n) ) + (negligible far tail)
```

As a cross-check, `statsmodels`' `NormalIndPower` with Cohen's h = 2·asin√p₂ − 2·asin√p₁ gives a
sample size within 2% of the formula above (tested in `tests/design/test_power.py`).
