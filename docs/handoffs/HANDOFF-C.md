# HANDOFF-C — Experiment design & power analysis

## What was built
- `src/retrylab/design/power.py`: `required_n_per_arm`, `mde_for_n` (Brent's method),
  `achieved_power`, plus `statsmodels_n_per_arm` (NormalIndPower + Cohen's h cross-check).
- `src/retrylab/design/report.py`: builds the C5 payload from fixed design assumptions and draws
  `reports/figures/power_curve.png`. `src/retrylab/design/__main__.py`: CLI.
- `docs/experiment_design.md`: the nine-section pre-registration, with the power math in an appendix.
- `tests/design/`: hand-formula, statsmodels, round-trip, C5 key/type, CLI determinism, and a
  doc test that fails if any number in the doc is not traceable to `power_analysis.json`.

## How to run
```bash
python -m retrylab.design --out reports/power_analysis.json   # also writes reports/figures/power_curve.png
pytest tests/design                                           # ~2s
```
Relative paths resolve from `PROJECT_ROOT` (falls back to cwd). `--no-figure` skips the PNG.
Output is byte-identical across runs.

## Key numbers (for F's memo)
| | |
|---|---|
| Baseline recovery rate | 34.5% (historical decline mix × historical recovery) |
| Target MDE | 2.0pp, α = 0.05 two-sided, 80% power |
| Required n per arm | **8,985** (statsmodels/Cohen's h: 8,984.3) |
| Planned n per arm | **25,000** |
| Power at 2.0pp with 25,000/arm | **99.7%** |
| MDE at 25,000/arm | **1.20pp** |
| MDE in `insufficient_funds` (11,250/arm) | 1.86pp |

## Decision rules in three sentences
If the SRM check fails (χ² p < 0.001) or either guardrail is breached (billing ticket rate up by
more than 0.5pp, or any confident increase in involuntary churn), we don't ship. If the overall
recovery lift is positive and significant and no segment is significantly negative after
Benjamini–Hochberg, we ship to everyone. Otherwise we ship only to the segments that are
significantly positive after BH, and if there are none we don't ship.

These match PRD-D's `decide.py` order exactly.

## Open issues / contract flags
1. **Additive C5 keys.** `power_analysis.json` also has `baseline_components` (decline mix ×
   recovery behind the 34.5% baseline) and `segment_mde` (per-segment n and MDE at the planned
   n, for the 18 pre-declared segments). All C5 keys and types are unchanged; consumers that
   validate C5 strictly (e.g. a Pydantic model with `extra="forbid"`) should allow extras.
2. **`.gitignore` ignores `reports/*.json`, `reports/figures/*.png` and `HANDOFF-*.md`.**
   `power_analysis.json`, `power_curve.png` and this file were force-added so D/E/F can read them
   without running C first. F may want to drop those ignore lines (same flag as HANDOFF-A #3).
3. **Design assumptions are hardcoded** in `report.py` (decline and segment mix, matching
   `config/sim.yaml`) rather than read from the simulator config, so C depends on contracts only.
4. **Guardrail breach definition.** The doc uses D's rule: breached when the CI lower bound is
   above the threshold. With a 0.0 threshold for involuntary churn that means "confidently any
   increase".
