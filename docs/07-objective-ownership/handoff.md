# Handoff — milestone 07 objective-ownership

## Next session start here
Branch off `main` (branch-first), then execute slice **07-02 seed-SMILES plumbing** (FR-001) — the 6-layer fix so an operator can bring their own starting compounds; a custom seed ⇒ `exploratory` (routes through `derive_mode`, now live). Deliverables (per plan Task 07-02):
1. Alembic revision (chain from head `f8342ecfc066`): `Run.seed_smiles` (nullable JSON/text), `Run.seed_source` (`default`|`custom`).
2. `api.ts` `CreateRunBody` + `Launcher.tsx:126-136` include `plan.seed_smiles` in the `createRun` body.
3. `CreateRunRequest` (+ `seed_smiles: list[str] | None`) with an **RDKit-validating field validator at the `/runs` boundary** (a client can POST directly — don't rely on intent-preview validation).
4. `RunConfig` (+ `seed_smiles`, `seed_source`); `create_run` insert; route the seed through `derive_mode(seed_smiles=...)` so a custom seed ⇒ exploratory.
5. `loop/state.py` `LoopState` (+ seed-population key); `loop/graph.py:48-50` gen-0 branch builds the population from RDKit-validated + canonicalized operator seeds (GA-filled from the pool or truncated to exactly `pop_size`; keep ≥2 parents for crossover) instead of `_load_starting_pop`; `loop/seeds.py` validate/canonicalize helper.
6. Test `test_seed_plumbing.py`: operator seed reaches gen-0 population; invalid SMILES rejected at `/runs`; custom seed forces exploratory; **integer RNG `seed` untouched** (reproducibility contract).

Then 07-03…07-08 per `docs/07-objective-ownership/milestone.md` + the plan `docs/superpowers/plans/2026-07-03-capychem-production-v1.md`.

## Current state
- Slice **07-01 shipped** on branch `m07-01-run-mode-split` (mode split + `figure_canon` + baseline gate + badge everywhere). Alembic head is now **`f8342ecfc066`**; the dev DB is upgraded (571 rows backfilled `mode="benchmark"`). 07-02's migration chains from this head.
- Gate all green: mypy · ruff · 325 backend · web typecheck/ESLint · 38 vitest · axe 10/10.
- Branch `main` is 10 commits ahead of `origin/main` (m06 + m07 docs, unpushed) + one uncommitted `CLAUDE.md` convention line (unrelated to 07-01).

## Active concerns
- **Mode split is live — every exploratory feature (07-02/03/04) must route its input through `derive_mode` AND ship its enforcement test.** The gate is `_gated_baseline(mode, task)` in `routes_runs.py`; `RunSnapshot/RunListItem/CompareRun.mode` are required (never defaulted).
- **07-02 must not touch the integer RNG `seed`** — seed-SMILES is a population source, not the RNG seed. Keep G6 reproducibility intact; test it.
- **Figure canon:** `figure_canon` exists but isn't wired into README/manifest yet (that's 07-06/07-08). Never "21/23"; derive every new figure surface from it.
- **Local schema drift:** `create_all` never ALTERs; after any model column change, `alembic upgrade head` the dev DB (CI runs fresh Postgres, so `test_migrations.py` gates there).
- **Trust ships WITH the pluggable seam** (07-05 alongside 07-03/04), not after.
