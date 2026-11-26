# PRD-C — Experiment Design & Power Analysis

**Owner paths:** `src/retrylab/design/`, `docs/experiment_design.md`, `reports/power_analysis.json`, `tests/design/`
**Produces:** `reports/power_analysis.json` (C5), `docs/experiment_design.md`
**Depends on:** contracts only (the baseline is a design assumption, not computed from the data)

## 1. Goal
Write the experiment's **pre-registration** before any results exist: hypothesis, metrics, guardrails, sample size, decision rules, and known risks. Interviewers often probe this part, so it has to read like a real experiment doc written at Stripe.

## 2. Non-goals
Don't analyze the actual experiment data (D does that). Don't read `config/ground_truth.yaml`.

## 3. Requirements

### 3.1 Power module — `src/retrylab/design/power.py`
- `required_n_per_arm(p_baseline, mde_abs, alpha=0.05, power=0.8, two_sided=True) -> int`: two-proportion z-test, normal approximation, rounded up.
- `mde_for_n(p_baseline, n_per_arm, alpha, power, two_sided) -> float`: the inverse, solved numerically.
- `achieved_power(p_baseline, mde_abs, n_per_arm, alpha, two_sided) -> float`
- Cross-check `required_n_per_arm` against `statsmodels.stats.power.NormalIndPower` with Cohen's h, within 2%.
- CLI: `python -m retrylab.design --out reports/power_analysis.json` writes C5 with these inputs: baseline 0.345 (the blended rate from historical decline mix × historical recovery), MDE 0.02, alpha 0.05, power 0.8, planned n 25,000/arm, and an MDE curve for n ∈ {2.5k, 5k, 10k, 15k, 20k, 25k}.
- Also save `reports/figures/power_curve.png` (MDE vs. n per arm, with the planned n marked). **Exception to ownership:** C may write this one file under `reports/figures/`.

### 3.2 Pre-registration — `docs/experiment_design.md`
Sections (all required):
1. **Background:** why failed payments matter (involuntary churn), and what "smart retries" means.
2. **Hypothesis:** H0/H1 for the primary metric, stated precisely.
3. **Unit of randomization & analysis:** customer-level randomization, invoice-level analysis (1:1 here, so no clustering correction is needed; explain why).
4. **Metrics:** primary `recovery_rate`; secondary `recovered_revenue_per_invoice`, time to recovery; guardrails `billing_ticket_rate` (+0.5pp max) and `involuntary_churn_rate` (no increase). Link each to the dbt metric names from C4.
5. **Sample size & duration:** a table from `power_analysis.json`, and the reason 25k/arm was chosen (powered for segment-level reads, not just the overall effect).
6. **Analysis plan:** two-proportion z-test with a Wald or Newcombe CI; CUPED with `pre_failed_attempt_rate`; a pre-declared segment list; Benjamini–Hochberg correction; an SRM check (χ², p < 0.001 = invalid).
7. **Decision rules:** ship / ship segmented / don't ship, as explicit if-then rules, including what happens if a guardrail is breached.
8. **Risks & mitigations:** peeking (fixed horizon, no early stopping), novelty effects, card-network retry limits, interference (none expected), and the fact that the data is simulated.
9. **Pre-registration statement:** this document was finalized before results were computed.

Keep it to about 2–3 pages. Write for a PM reader, and give the math in an appendix.

## 4. Acceptance criteria
- [ ] `power_analysis.json` validates against C5 (keys/types). `required_n_per_arm` is within ±1% of the hand formula, and it agrees with statsmodels within 2%.
- [ ] `mde_for_n(required_n_per_arm(...))` round-trips to the input MDE within 1e-4.
- [ ] All nine sections are present in `experiment_design.md`, and every number in it comes from `power_analysis.json` (a test greps for consistency).
- [ ] `pytest tests/design` and `ruff check` pass.

## 5. Handoff
`HANDOFF-C.md`: the key numbers (required n, MDE at the planned n) and a 3-sentence summary of the decision rules for F's memo.
