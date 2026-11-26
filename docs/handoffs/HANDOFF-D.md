# HANDOFF-D — Statistical analysis

## What was built
`src/retrylab/analysis/`:

| module | what it does |
|---|---|
| `io.py` | Reads `main.fct_experiment_invoices` from DuckDB **read-only**; reads C5 and falls back to the C5 defaults (with a `UserWarning`) if the file is missing. Paths resolve from `PROJECT_ROOT`. |
| `srm.py` | χ² goodness-of-fit vs. 50/50; `passed = p ≥ 0.001`. |
| `proportions.py` | Pooled two-proportion z-test; Wilson interval; Newcombe hybrid-score (method 10) CI on `treatment − control`. |
| `means.py` | Welch t-test with Welch–Satterthwaite CI. |
| `cuped.py` | θ = cov(Y,X)/var(X) on pooled data, `Y_adj = Y − θ(X − X̄)`, Welch test on `Y_adj`; `variance_reduction_pct = 100·(1 − var(Y_adj)/var(Y))`. |
| `segments.py` | Per-(dimension, value) lift/CI/p for every C2 segment; BH across all rows; `significant_adj = p_adj < 0.05`. |
| `guardrails.py` | Lift/CI for `billing_ticket_rate` (`had_billing_ticket_14d`) and `involuntary_churn_rate` (`churned_involuntary_30d`); `breached = ci_low > threshold_abs`. |
| `impact.py` | Annualized incremental revenue with explicit `assumptions`. |
| `decide.py` | The decision rules (below). |
| `figures.py` | The three PNGs (150 dpi, 8×5 in, gray `#8A8F98` / blue `#3366CC`). |
| `schema.py` | Pydantic model mirroring C6 (`extra="forbid"`, strict types). Every run validates against it. |
| `run.py` | `build_results(df, power)` (pure) and `run_analysis(db, out, ...)` (I/O). |
| `__main__.py` | CLI. |

`tests/analysis/` — `fixtures/make_fixture_db.py` (C4-shaped DuckDB with planted effects, default
4,000 rows, +5pp for `insufficient_funds`, 0 elsewhere), reference tests vs. scipy/statsmodels
(1e-6), property tests (A/A coverage over 200 seeds, SRM, CUPED ρ=0.5 → 25%±5, planted effect
recovered at 50k), one test per decision branch, end-to-end/determinism/figure/runtime tests.

## How to run
```bash
python -m retrylab.analysis --db data/warehouse.duckdb --out reports/
python -m retrylab.analysis --db data/warehouse.duckdb --out reports/ --frozen-time 2026-04-15T12:00:00Z
#   --power PATH   (default: <out>/power_analysis.json)   --no-figures
pytest tests/analysis        # 64 tests, ~7s
ruff check src/retrylab/analysis tests/analysis
python tests/analysis/fixtures/make_fixture_db.py --out /tmp/fixture.duckdb   # standalone fixture
```
Outputs: `reports/results.json` and `reports/figures/{lift_overall,segment_forest,recovery_by_day}.png`.
With `--frozen-time`, both the JSON and the PNGs are byte-identical across runs. 50k rows run in
under 1s (well inside the 30s budget).

## Figures
- **`lift_overall.png`** — the primary lift (pp) with its 95% CI, raw (z-test + Newcombe) above and
  CUPED-adjusted below, with a dashed zero line. Title states the lift and CUPED's variance cut.
- **`segment_forest.png`** — forest plot of every segment's lift and 95% CI, in C2 order.
  BH-significant segments are blue, others gray. Title states how many are significant and the
  largest one.
- **`recovery_by_day.png`** — cumulative % of failed invoices recovered by days since failure
  (0–7, hourly steps), per variant. Title states the day-7 rates and the gap.

## Decision logic as implemented (`decide.py`)
First matching rule wins. "Significant" = `p < alpha` from C5 (default 0.05); segment
significance is BH-adjusted.
1. SRM failed → `do_not_ship`, rationale says "invalid experiment".
2. Any guardrail `breached` → `do_not_ship`.
3. Overall lift significant **and** positive, and **no** segment significantly negative → `ship`.
4. Otherwise, any segment significantly positive → `ship_segmented` (covers both "overall not
   significant" and "overall significant but some segment is significantly hurt").
5. Otherwise → `do_not_ship`.

Revenue impact: `ship` → overall abs lift × all experiment invoices × mean amount × 12.
`ship_segmented` → Σ over shipped segments of abs lift × segment invoices × segment mean amount ×
12. `do_not_ship` → 0.

## Sanity check on the real simulator output
I built a throwaway `fct_experiment_invoices` straight from A's 50k parquet (not B's dbt — my own
SQL, so B's numbers may differ slightly) and ran the analysis: SRM passed (p=0.89); recovery
34.85% → 38.12%, **+3.27pp [2.42, 4.11]**; CUPED +3.30pp [2.49, 4.11], variance −8.1% (matches
A's corr of −0.285, so ρ² ≈ 8%); `insufficient_funds` +6.8pp (A planted ≈ +7.2pp); no guardrail
breached (churn actually falls by 2.1pp); decision **`ship`**, ≈ $491k/yr.

## Open issues / contract flags
1. **`ship_scope` when nothing ships.** C6 only lists `"all" | "segments"`. For `do_not_ship` I
   emit `"segments"` with `ship_segments: []` and revenue 0. For `ship`, `ship_segments` is `[]`.
   If E/F want a `"none"` value, C6 needs to change.
2. **Overlapping segments.** Segments from different dimensions overlap (a US debit card is in
   both), so summing every positive segment double counts. For `ship_segmented` I ship the
   significant positive segments of the single dimension with the largest total impact, and say
   so in `assumptions`.
3. **6-decimal rounding of p-values.** Per PRD-D §3.2 all floats are rounded to 6 dp, so very
   small p-values serialize as `0.0` (the real run's primary p is `0.0`). E/F should display
   these as "p < 0.000001", not "p = 0".
4. **Secondary metrics.** C6's `secondary` is a list; I emit `recovered_revenue_per_invoice_usd`,
   `avg_retries_per_invoice` (Welch on all invoices) and `hours_to_recovery` (Welch on recovered
   invoices only; time to recovery is a secondary metric in PRD-C).
5. **Missing segment values.** A C2 segment value with no invoices in one arm is skipped (there is
   no defined lift); with real data all 18 are present.
6. CUPED is applied to the binary `is_recovered` with a pooled θ; its CI is a Welch CI on `Y_adj`
   (θ's estimation error is ignored, standard practice at this n).
7. The figure tests use Pillow, which ships with matplotlib; no new dependency.
8. `.gitignore` still ignores `HANDOFF-*.md` (A flagged this too); this file was force-added.
