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
