# Handoff — milestone 07 objective-ownership

## Next session start here
Branch off `main` (branch-first), then execute slice **07-03 pluggable oracle**
(plan Task 07-03). Create `packages/core/capychem/oracle/` package:
1. `protocol.py` — `ScoringOracle` Protocol: `score(smiles: list[str]) -> list[float | None]`
   + metadata `name`, `version`, `direction` (`maximize`|`minimize`), optional
   `applicability_domain(smiles) -> float`.
2. `registry.py` — name→oracle registry.
3. `pmo.py` — `PmoOracle(task)` wrapping the existing `oracle.score_smiles` /
   `score_batch_async`; **parity test = byte-identical scores** to the current path.
4. `descriptors.py` — SA-score (RDKit `Contrib/SA_Score`), QED, MW/logP/TPSA (zero new deps).
5. `admet.py` — ADMET-AI, **import-guarded** so the stub path never needs it.
6. Thread `direction` into `logic.merge_and_truncate` / `_sort_key` and `top_auc`
   (default `maximize` = today's behavior) so a `minimize` oracle isn't silently inverted.
7. Any custom/non-PMO oracle ⇒ `mode=exploratory` (route through `derive_mode`).
Test `test_oracle_protocol.py`: registry round-trip, PMO parity, descriptor oracles,
direction correctness. **Trust layer (07-05) ships WITH the pluggable seam** — keep it
in view but 07-03 is the oracle protocol first.

Then 07-04…07-08 per `docs/07-objective-ownership/milestone.md` + the plan.

## Current state
- Slice **07-02 shipped** (merged to `main`): seed-SMILES plumbing (FR-001). Alembic head
  is now **`b4ea6a051441`** (`Run.seed_smiles` JSON + `Run.seed_source`); dev DB upgraded.
  Custom seed ⇒ `exploratory` via `derive_mode(seed_smiles=…)`; gen-0 builds the population
  from operator seeds (canon+dedup, topped up from the shipped pool to `pop_size`).
- Gate all green: mypy (53 files) · ruff · **336** backend · web typecheck/ESLint · 40 vitest ·
  migration drift gate. axe not re-run locally (07-02 was copy-only on an already-labeled
  field) — rides CI.
- `main` is ahead of `origin/main` (unpushed, as before) + the m07-02 commit.

## Active concerns
- **Mode split stays load-bearing:** 07-03/04 must route their new inputs (custom oracle,
  composed objective, constraints) through `derive_mode` AND ship the enforcement test.
  Gate is `_gated_baseline(mode, task)` in `routes_runs.py`.
- **PMO parity is a hard gate for 07-03:** `PmoOracle` must return byte-identical scores to
  the current `oracle.score_smiles` path (G6 / benchmark regression). Prove it with a test.
- **Two test roots share a rootdir with no `__init__.py`** — test file basenames must be
  unique across `packages/core/tests` and `apps/api/tests` (07-02 hit this: renamed the API
  file to `test_seed_plumbing_route.py`).
- **Schema drift:** after any model column change, `alembic upgrade head` the dev DB;
  new revisions chain from head `b4ea6a051441`.
- Rich seed-import UI (SDF/CSV, accepted/rejected) is deferred to **07-08**; 07-02 shipped a
  minimal space/comma-separated single field.
