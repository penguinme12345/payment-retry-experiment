# PRD-D — Statistical Analysis

**Owner paths:** `src/retrylab/analysis/`, `reports/results.json`, `reports/figures/` (except `power_curve.png`), `tests/analysis/`
**Consumes:** marts (C4), `reports/power_analysis.json` (C5, for guardrail thresholds) · **Produces:** `reports/results.json` (C6), figures
**Depends on:** contracts only. Build against your own fixture DuckDB.

## 1. Goal
Run the pre-registered analysis rigorously and output one machine-readable results file that the dashboard and memo read from. Correctness matters more than anything else here, because every number in the final memo comes from this module.

## 2. Non-goals
No reading `config/ground_truth.yaml`. No dashboards. No new metric definitions: use the mart columns as defined.

## 3. Requirements

### 3.1 Modules
| Module | Responsibility |
|---|---|
| `io.py` | Read the marts from DuckDB (read-only), read `power_analysis.json` and fall back to C5 defaults if it's missing |
| `srm.py` | χ² goodness-of-fit against 50/50; `passed = p ≥ 0.001` |
| `proportions.py` | Two-proportion z-test; abs/rel lift; 95% CI on the difference (Newcombe hybrid score) |
| `means.py` | Welch t-test and CI for continuous metrics (recovered revenue per invoice) |
| `cuped.py` | CUPED: θ = cov(Y, X)/var(X) on pooled data, Y_adj = Y − θ(X − mean X); report the adjusted lift/CI and `variance_reduction_pct = 100·(1 − var(Y_adj)/var(Y))` |
| `segments.py` | Per-segment lift/CI/p for every (dimension, value) in C2; Benjamini–Hochberg `p_value_adj`; `significant_adj = p_adj < 0.05` |
| `guardrails.py` | Lift and CI for guardrail metrics; `breached = ci_low > threshold_abs` (i.e., confidently worse than the allowed increase) |
| `impact.py` | Annualized incremental revenue = Σ over shipped segments of (abs lift × monthly failed invoices × avg amount) × 12; state every assumption in `assumptions` |
| `decide.py` | Apply C's decision rules: SRM fail → `do_not_ship` with rationale "invalid experiment"; any guardrail breached → `do_not_ship`; overall significant and positive, with no segment significantly negative → `ship`; otherwise, if some segments are significantly positive → `ship_segmented`; else `do_not_ship` |
| `figures.py` | Save PNGs: `lift_overall.png` (point + CI, raw and CUPED), `segment_forest.png` (forest plot by segment, BH-significant ones highlighted), `recovery_by_day.png` (cumulative recovery curve by variant over 7 days) |
| `__main__.py` | `python -m retrylab.analysis --db data/warehouse.duckdb --out reports/` |

### 3.2 Output
`reports/results.json` must exactly match C6's keys, nesting, and types. Round floats to 6 decimals. `generated_at` is ISO-8601 UTC, and a `--frozen-time` flag fixes it for deterministic tests.

### 3.3 Figure style
Matplotlib, 150 dpi, 8×5 in, colorblind-safe two-color palette (control gray `#8A8F98`, treatment blue `#3366CC`), labeled axes with units, a title that states the finding (e.g., "Smart retries lift recovery by 3.2pp"), no chart junk.

### 3.4 Fixtures & tests
- `tests/analysis/fixtures/make_fixture_db.py`: builds a small DuckDB with C4-shaped marts and **known** effects (e.g., 4,000 rows, +5pp in one segment, 0 elsewhere).
- Unit tests that compare each statistical function to `scipy`/`statsmodels` reference results on hand-computed examples, within 1e-6.
- Property tests: an A/A fixture (no effect) gives a lift CI containing 0 in ≥93% of 200 seeded runs; an SRM fixture fails the SRM check.
- CUPED test: with a covariate correlated at ρ=0.5, variance reduction ≈ 25% (±5).

## 4. Acceptance criteria
- [ ] `results.json` validates against a Pydantic model in `src/retrylab/analysis/schema.py` that mirrors C6.
- [ ] Every statistical function matches reference implementations within 1e-6.
- [ ] The A/A coverage, SRM, and CUPED property tests pass.
- [ ] The decision logic is covered by a test for each branch.
- [ ] The three figures are created and are non-empty.
- [ ] `pytest tests/analysis` and `ruff check` pass. Full runtime under 30s on 50k rows.

## 5. Handoff
`HANDOFF-D.md`: how to run it, a description of each figure, and the decision logic as implemented.
