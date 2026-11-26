# HANDOFF-F — Integration, decision memo & CI (phase 1)

## What was built
- `src/retrylab/reporting/`
  - `formatting.py` — `pp` (`3.2pp`), `signed_pp`, `pct` (`34.5%`), `money` (`$1.2M` / `$48,300` /
    `$8.75`), `ci_pp` (`[2.4pp, 4.0pp]`), `ci_money`, `pvalue`, `count`.
  - `labels.py` — plain-English metric and segment phrasing ("Customers declined for insufficient
    funds", "Customers in the UK", …).
  - `context.py` — turns `results.json` (C6) + `power_analysis.json` (C5) into a formatted
    context; picks the narrative branch (`ship`, `ship_segmented`, `do_not_ship` split into
    SRM failure / guardrail breach / no effect).
  - `templates/memo.md.j2` — the memo: TL;DR, what we tested, results (primary + CUPED + SRM +
    secondary), where it works, guardrails, recommendation & rollout, caveats, figures. No
    numbers in the template (a test enforces this). Figures from `reports/figures/` are embedded
    only if the PNG exists.
  - `render.py`, `__main__.py` — `python -m retrylab.reporting --results … --power … --out …`.
  - `bullets.py` — `python -m retrylab.reporting.bullets`: three resume bullets < 160 chars.
  - `readme.py` — `python -m retrylab.reporting.readme`: fills the README's
    `<!-- BEGIN:x -->…<!-- END:x -->` blocks (headline, key-results, bullets) from results.json.
- `Makefile` — every PRD target plus `readme` and `bullets`; `SIM_CONFIG` override (CI uses
  `config/sim.ci.yaml`, which A already created).
- `.github/workflows/ci.yml` — `lint-test` job (setup → lint → test) and a `pipeline` job
  (`make all` at 5k, uploads `reports/` + `docs/memo.md`). The pipeline job is
  `continue-on-error` until B–E are merged; remove that in phase 2.
- `README.md` — portfolio skeleton with generated blocks and a Mermaid architecture diagram.
- `pyproject.toml` — ships `reporting/templates/*.j2` as package data.
- `tests/integration/`
  - fixtures: `power_analysis.json` and `results_{ship, ship_segmented, do_not_ship,
    do_not_ship_srm, do_not_ship_guardrail}.json`.
  - `test_memo.py`, `test_formatting.py`, `test_readme_bullets.py` — 47 tests.
  - `test_end_to_end.py` (`slow`) — the phase-2 assertions; skips until the dbt project,
    design, analysis and export entry points exist.

## How to run
```bash
make memo                     # needs reports/results.json + reports/power_analysis.json
python -m retrylab.reporting --results tests/integration/fixtures/results_ship.json \
  --power tests/integration/fixtures/power_analysis.json --out /tmp/memo.md
pytest tests/integration      # ~0.5s; e2e skipped until phase 2
```

## Preview
A memo rendered from a quick results file computed directly on the default 50k simulator output
(not D's analysis; illustrative C5 numbers) recommends **ship**: recovery 34.9% → 38.1%
(+3.3pp, CI [2.4pp, 4.1pp]), insufficient-funds +6.8pp, no guardrail breached. Bullets from that
run:
- Designed and analyzed a 50,000-customer A/B test of smart payment-retry timing; recovery rate
  moved +3.3pp (95% CI [2.4pp, 4.1pp], p < 0.001).
- Built a dbt + DuckDB metrics layer and Python stats pipeline with CUPED (8.1% variance cut) and
  BH-corrected cuts: 11 of 18 segments significant.
- Wrote a decision memo and Streamlit dashboard recommending a full launch, sized at
  $490,900/yr in recovered revenue.

## Open issues / for phase 2
1. **`--frozen-time` form (D).** PRD-D doesn't say whether it's a bare flag or takes a timestamp.
   The reproducibility test reads `--help` and supports both.
2. **Schema model name (D).** The e2e test validates against the first Pydantic model in
   `retrylab.analysis.schema` that has a `recommendation` field.
3. **dbt and `PROJECT_ROOT` (B).** The e2e test runs `make all` in a scratch copy of the repo
   with `PROJECT_ROOT` pointing there; dbt profiles must resolve the DuckDB/raw paths from it.
4. **`.gitignore` ignores `HANDOFF-*.md`** (bootstrap), which conflicts with ground rule 7. This
   file was force-added, like HANDOFF-A. `.gitignore` isn't in any workstream's paths.
5. **Lift ranking in "Where it works".** With a broad effect most segments are significant, so the
   memo lists the 4 with the strongest evidence (lowest adjusted p, then largest lift) and states
   "N of M segments improved". Revisit once real D output exists.
6. **Memo length.** Renders at ~450–630 words depending on the branch; the PRD target is ~500.
7. Phase 2 still to do: run `make clean all`, drop `continue-on-error`, add dashboard screenshots,
   run `make readme`.

---

# Phase 2 — integration (done)

## What changed
- Merged A–F into `main` (PR 6 first, then 1, 2, 5, 4, 3). No merge conflicts.
- `make all` now runs simulate → dbt → design → analyze → memo → export → readme, ~15s at 50k.
  `make clean all` passes from a fresh clone.
- CI: the `pipeline` job is no longer `continue-on-error` and runs `make clean all` at 5k from a
  clean checkout. Push builds are limited to `main`; PRs still build on every push.
- The end-to-end and reproducibility tests (`tests/integration/test_end_to_end.py`) now run instead
  of skipping. Full suite: 263 tests.
- Generated outputs are committed so the repo reads well without running anything:
  `docs/memo.md`, `reports/results.json`, `reports/figures/*.png`. `.gitignore` no longer hides
  them or the handoff files. Handoffs moved to `docs/handoffs/`.
- README rewritten around real numbers, dashboard and forest-plot screenshots, quickstart and a
  command table. Dashboard screenshots re-captured from the real run.

## Cross-piece mismatches fixed
1. `hours_to_recovery` (D) was formatted as a percentage in the memo ("7103.1%"). It now renders
   in hours (`71.0h → 47.0h`).
2. README key-results showed raw guardrail metric names; they now use the memo's labels.
3. README listed top segments by raw lift (surfacing Australia), while the memo ranks by evidence.
   Both now use the memo's ranking (lowest BH-adjusted p, then lift).
4. Dashboard showed `$490,940` against `$490,900` in the memo and README. The dashboard KPI now
   rounds the same way.
5. Dashboard secondary-metrics table used raw column names and showed p-values as `0.0000`; it now
   uses readable labels and `< 0.001`.

## Still open
- The memo renders at ~800 words on the `ship` branch, above the ~500 target.
- `ship_scope="segments"` with an empty list on `do_not_ship` (D's flag) is unchanged; nothing
  downstream misreads it.
