# Handoff — milestone 07 objective-ownership

## Next session start here
Branch off `main` (branch-first), then execute slice **07-01 run-mode-split** — the benchmark/exploratory invariant every other 07 feature depends on. Deliverables:
1. Alembic revision (chain from head `f4251d568ae6`): `Run.mode` (`benchmark`|`exploratory`, default benchmark), `Run.objective_json` (nullable), `Run.constraints_json` (nullable).
2. `packages/core/capychem/mode.py` `derive_mode(*, objective_json=None, constraints_json=None, seed_smiles=None)` — exploratory if ANY exploratory input present, else benchmark (later slices route their inputs through it; at 07-01 all runs derive to benchmark). Mode is server-derived, never client-set.
3. **G1-contamination guard:** in `routes_runs.py` snapshot building (~:207 live, ~:231 DB), set `graph_ga_baseline = graph_ga_baseline(task) if mode == "benchmark" else None`. An exploratory run must never present a Graph-GA "beat". Add `mode` to `RunSnapshot`/`RunListItem`.
4. `packages/core/capychem/figure_canon.py` — single honest-figure source (21 comparable, 2 excluded, 9 decisive; never "21/23"). A test fails if any surface prints "21/23".
5. A mode badge on every web run surface (Overview, RunsBrowse, Cockpit, Compare); exploratory reads "not benchmark-comparable". Don't reuse the coral `--primary`.
6. Regression: the benchmark path must stay byte-identical (existing suite green); a test proves an exploratory snapshot drops the baseline while a benchmark one keeps it.

Then 07-02…07-08 per `docs/07-objective-ownership/milestone.md` + the plan `docs/superpowers/plans/2026-07-03-capychem-production-v1.md`.

## Current state
- Branch `main`: milestone 06 shipped + merged (`27f005b`..`968dc5d`), **not pushed** (`origin/main` is behind — push when ready). Working tree has one uncommitted change: the `CLAUDE.md` convention update.
- Engine production-grade: CI-gated (backend + web + axe), WCAG-AA, Alembic-migrated (head `f4251d568ae6`; new columns go through migrations chained from head — `create_all` is test-only), fault-tolerant (pause + retry + durable G6-exact resume). 303 backend + 30 web + 10 axe tests green with the harness present.
- No 07 code started. The vault paste-prompt `prompts/capychem/2026-07-05-…-milestone-07-objective-ownership-handoff.md` mirrors this handoff.

## Active concerns
- **Mode split is load-bearing — enforce in code + tests, not convention.** The whole honesty story + G1 pristineness depends on it; ship every exploratory feature WITH its enforcement test.
- **Figure canon:** every new doc/badge/manifest derives from `figure_canon` (2 excluded). Never "21/23"; no SOTA/multi-seed/real-world-efficacy claims (N6).
- **Trust ships WITH the pluggable seam** (07-05 alongside 07-03/04), not after — the custom oracle increases reward-hacking risk.
- **Execution (repo learning):** run build subagents synchronously; independently re-verify every self-reported check against source (Critics caught 3 real defects in m06 — mypy is the real typecheck, pyright import-warnings are venv noise); orchestrator owns doc writes; reuse existing agents.
- **Sizing:** 8 slices is over the guideline — split a slice past 2 pages (fold 07-06 into 07-07; spin 07-08 into its own UI milestone).
