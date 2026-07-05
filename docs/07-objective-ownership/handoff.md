# Handoff — milestone 07 objective-ownership

## Completed this session
- Milestone 06 (production-hardening) shipped and **merged to `main`** (8 commits, `27f005b`..`968dc5d`): repo hygiene + honest docs + LICENSE, CI (backend + web + axe), WCAG-AA a11y + axe gate, Alembic baseline, reliability (recoverable pause + retry + Modal n>1 fix + durable G6-exact resume). App verified up and running end to end via the live API.
- Stood up this milestone folder (milestone.md + this handoff) and marked 07 `← active` in `docs/milestones.md`.

## Slice status across milestone
- 07-01 run-mode-split → planned (start here)
- 07-02 seed-smiles-plumbing → planned
- 07-03 pluggable-oracle → planned
- 07-04 objective-composition → planned
- 07-05 quality-trust-layer → planned
- 07-06 provenance-manifest → planned
- 07-07 lineage-export → planned
- 07-08 objective-authoring-ui → planned

## Current state
- Branch: `main` (milestone 06 merged; **not pushed to origin** — `origin/main` is 8 commits behind; push when ready).
- Engine: production-grade. Alembic is live — schema head `f4251d568ae6` (adds `Run.max_generations`); the dev Postgres is at head. New columns MUST go through Alembic revisions chained from head, never `create_all`-drift.
- CI: `.github/workflows/ci.yml` gates backend (ruff/mypy/pytest, builds the harness) + web (lint/typecheck/test) + axe-core (5 routes × light/dark). Keep it green.
- Tests: `303` backend + `30` web + `10` axe, all green with the harness present.
- Cost/verification budget is near-free (<$50 TOTAL); finishability is the binding risk. No expensive-oracle-in-loop, no GPU training, no auth/hosting.

## Next session start here
Execute slice **07-01 run-mode-split** — the benchmark/exploratory invariant every other 07 feature depends on. Steps:
1. Alembic revision (chain from `f4251d568ae6`): add `Run.mode` (`benchmark`|`exploratory`, default `benchmark`), `Run.objective_json` (nullable), `Run.constraints_json` (nullable). Update `db/models.py` + `RunConfig` + `CreateRunRequest`/snapshot.
2. **Enforcement in code + tests (not just docs):** the API refuses to tag a run `benchmark` if any exploratory feature is present; eval ingestion (`packages/core/capychem/eval/*`) only ingests `mode==benchmark` into `top_auc`/baselines. A composed/custom/custom-seed run cannot be `benchmark`.
3. `packages/core/capychem/figure_canon.py` — single source stating "21 comparable, 2 excluded" (derived from `docs/04-compare-and-polish/g1-full23-10k-seed42.json` but stating the prose canon; the JSON's `g1_verdict` says "1" because sitagliptin was pre-excluded upstream — do NOT read `excluded_rows` length). A test fails if any surface prints "21/23".
4. A prominent `benchmark`/`exploratory` badge on every run surface (Overview, RunsBrowse, LiveRun/Cockpit, Compare); exploratory carries "not benchmark-comparable".
5. Regression gate: `benchmark`-mode eval reproduces the committed G1 numbers unchanged.

Then proceed through 07-02…07-08 per `docs/07-objective-ownership/milestone.md` + the plan `docs/superpowers/plans/2026-07-03-capychem-production-v1.md`.

## Active concerns
- **Mode split is load-bearing and must be enforced in code + tests, not convention** — the whole honesty story (and G1 pristineness) depends on it. Ship every exploratory feature WITH its enforcement test.
- **Figure canon:** every new doc/badge/manifest derives from `figure_canon` (2 excluded), never a naive JSON read. Never "21/23"; no SOTA/multi-seed/real-world-efficacy claims (N6).
- **Trust ships with the seam:** the pluggable oracle *increases* reward-hacking risk — the quality/canary layer (07-05) is mandatory in the same phase as custom oracles, not deferred.
- **Alembic discipline:** every schema change = a migration chained from head + a models.py update; `create_all` is now test-only.
- **Execution (repo learning):** run build subagents synchronously / via file-write handoff; independently re-verify every self-reported check (Critics caught 3 real defects in m06); orchestrator owns all doc writes; reuse existing agents. Adversarially verify — the ultracode multi-agent build/critic loop worked well in m06.
- **Sizing:** 8 slices is over the guideline; split a slice if it grows past 2 pages (candidates: fold 07-06 into 07-07; spin 07-08 into its own UI milestone).
