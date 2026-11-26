# RetryLab — Subscription Payment Recovery Experiment

**Project overview & agent orchestration guide**

## 1. What we're building

An end-to-end analytics project that simulates a subscription business's failed card payments, runs an A/B test of **smart retry timing** (treatment) against a **fixed retry schedule** (control), and turns the result into a metrics layer, a statistical analysis, a dashboard, and a decision memo.

The project exists to show the skills listed in a Stripe Data Analyst internship posting:

| Posting requirement | Where it's shown |
|---|---|
| Analyze data and run experiments | PRD-C (design), PRD-D (analysis) |
| A/B testing to assess launch impact | PRD-C, PRD-D |
| Extend a metrics semantic layer | PRD-B (dbt semantic models + metrics) |
| Build/improve data assets | PRD-A (raw data), PRD-B (marts) |
| Metrics, reports, dashboards | PRD-B, PRD-E |
| Actionable recommendations / data storytelling | PRD-F (memo) |
| Writing and debugging data pipelines | PRD-A → PRD-B → PRD-D, orchestrated by PRD-F |

**Business question:** *Does retrying failed subscription payments at "smart" times (e.g., just after the customer's payday) recover more revenue than a fixed day-1/3/5/7 schedule, without hurting customers? If so, for which segments should we ship it?*

## 2. Workstreams

| PRD | Workstream | Owns (only these paths) | Depends on |
|---|---|---|---|
| A | Data simulation | `src/retrylab/sim/`, `config/sim.yaml`, `config/ground_truth.yaml`, `tests/sim/` | Contracts only |
| B | dbt metrics layer | `dbt/`, `tests/dbt/` | Contracts only (uses its own fixtures) |
| C | Experiment design & power | `src/retrylab/design/`, `docs/experiment_design.md`, `reports/power_analysis.json`, `tests/design/` | Contracts only |
| D | Statistical analysis | `src/retrylab/analysis/`, `reports/results.json`, `reports/figures/`, `tests/analysis/` | Contracts only (uses its own fixtures) |
| E | Dashboard | `app/`, `exports/powerbi/`, `tests/app/` | Contracts only (uses its own fixtures) |
| F | Integration, memo & CI | `Makefile`, `README.md`, `pyproject.toml`, `.github/`, `src/retrylab/reporting/`, `docs/memo.md`, `tests/integration/` | Phase 1: contracts only · Phase 2: all of A–E merged |

**Every workstream can start at the same time.** They only meet at the interfaces in `01_CONTRACTS.md`, and each workstream tests against fixtures it builds itself to match those contracts. PRD-F starts with scaffolding (Makefile, CI, memo template) and does a final integration pass once A–E are merged.

```
          ┌──────────── 01_CONTRACTS.md ────────────┐
          │                                          │
   A: sim ──raw parquet──▶ B: dbt ──marts──▶ D: analysis ──results.json──▶ F: memo
                              │                                │
                              └──────marts──▶ E: dashboard ◀───┘
   C: design ──power_analysis.json──▶ D, E, F
```

## 3. Ground rules for every agent

1. **Read `00_OVERVIEW.md`, `01_CONTRACTS.md`, and your own PRD before writing code.**
2. **Only create or modify files inside the paths you own.** If you need a change somewhere else (a new dependency, a contract change), write it in `HANDOFF-<letter>.md` at the repo root and don't make the change yourself.
3. **Contracts are fixed.** Don't rename columns, tables, paths, or JSON keys. If a contract looks wrong, implement it as written and flag it in your handoff file.
4. **Test against your own fixtures.** Never wait for another workstream's real output. Put small hand-built fixtures that match the contract under `tests/<area>/fixtures/`.
5. **Be deterministic.** Seed all randomness. The same config must produce byte-identical outputs.
6. **Toolchain:** Python 3.11, `ruff` for lint/format (line length 100), `pytest` for tests, type hints on all public functions.
7. **Done means:** your PRD's acceptance criteria pass, `ruff check` is clean on your paths, `pytest tests/<area>` passes, and `HANDOFF-<letter>.md` lists what you built, how to run it, and any open issues.

## 4. Setup (run once, before launching agents)

```bash
bash bootstrap.sh retrylab     # creates the repo skeleton, pyproject, and copies these PRDs into docs/prd/
cd retrylab && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
git init && git add -A && git commit -m "Bootstrap RetryLab skeleton"
```

Give each agent its own branch or worktree (`git worktree add ../retrylab-A -b ws-a`, and so on), then merge them in this order: A → B → C → D → E → F (phase 2).

## 5. Launch prompt (one per agent)

> You are the agent for **PRD-{LETTER}** in the RetryLab repo. Read `docs/prd/00_OVERVIEW.md`, `docs/prd/01_CONTRACTS.md`, and `docs/prd/PRD-{LETTER}_*.md`. Implement everything in your PRD. Only modify the paths your PRD owns. Build your own fixtures that match the contracts; don't depend on other workstreams' outputs. When you finish, make sure every acceptance criterion passes and write `HANDOFF-{LETTER}.md`.

For PRD-F, run phase 1 in parallel with the others, then relaunch it after the merge with: *"Phase 2: all workstreams are merged. Complete PRD-F phase 2."*

## 6. End state

```bash
make all      # simulate → dbt build → power analysis → analysis → memo
make app      # launches the dashboard
make test     # all tests
```

This produces `reports/results.json`, `reports/figures/*.png`, `docs/memo.md`, a running Streamlit dashboard, and Power BI–ready CSV exports.
