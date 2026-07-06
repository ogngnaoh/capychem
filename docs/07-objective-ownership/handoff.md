# Handoff — milestone 07 objective-ownership

## Next session start here
Branch off `main` (branch-first), then execute slice **07-04b constraints** (the half
split out of plan Task 07-04). Build:
1. `packages/core/capychem/constraints.py`:
   - **Hard SMARTS include/exclude** via RDKit `FilterCatalog` (bundle the PAINS + Brenk
     catalogs) applied at the **validity gate** — the same path FR-005 uses, so a
     constraint-failing molecule is treated like an invalid one (dropped before scoring,
     GA-fallback keeps throughput). Custom SMARTS include/exclude patterns too.
   - **Soft property bands** (MW/logP/TPSA) expressed as `sigmoid`/`double_sigmoid`
     objective components (reuse `objective.apply_transform`) — a band is just a term.
   - A **constraint-starvation** signal distinct from FR-003 plateau: "no candidate
     satisfies the hard constraints this generation" (vs. plateau = "score stopped
     improving"). Surface it as its own stop_reason/status so the UI can say *why*.
2. Wire constraints into the loop: `Run.constraints_json` (column exists, 07-01) →
   `RunConfig`/`LoopState`/`runner`; apply hard filters in the validate/fallback path;
   any non-null constraints ⇒ `mode=exploratory` via `derive_mode(constraints_json=…)`
   (already a param). Route: `CreateRunRequest.constraints_json` + validator.
3. Tests: `test_constraints.py` (SMARTS include/exclude drop the right molecules;
   starvation ≠ plateau; benchmark path unaffected), mode-enforcement test.

Then 07-05 (quality + trust — ships WITH the pluggable seam, now landed) → 07-06 →
07-07 → 07-08, per `docs/07-objective-ownership/milestone.md` + the plan.

## Current state
- Slice **07-04 shipped** (merged to `main`): composed multi-term objective. New
  `packages/core/capychem/objective.py` (transforms `identity`/`sigmoid`/
  `reverse_sigmoid`/`double_sigmoid`/`value_map` → [0,1]; `weighted_sum`/`weighted_product`
  aggregators, single term == raw; `Objective.evaluate_async(smiles, pmo_scorer=…)` with a
  **dependency-injected** harness scorer so PMO terms keep the exact cost/backend path).
  Score node has a composed-objective branch (benchmark path byte-identical, same lines);
  `objective_json` threaded through `RunConfig`/`LoopState`/`runner`; `POST /objective/validate`;
  `derive_mode(objective_json=…)` ⇒ exploratory.
- Gate all green: mypy (59 files) · ruff · **362** backend (+16; all eval/benchmark tests
  byte-identical) · web untouched.
- Alembic head unchanged (`b4ea6a051441`); `Run.objective_json` column already existed (07-01),
  now populated. `main` ahead of `origin/main` (unpushed) + m07-02/03/04 commits.

## Active concerns
- **Benchmark stays byte-identical:** the score node's objective branch fires ONLY when
  `objective_json` is present; the no-objective path is the original code, unchanged. Keep it
  that way in 07-04b (constraints apply at the validate gate, not the benchmark score path).
- **Direction normalizes at the transform:** a `minimize` oracle in a composed objective uses
  `reverse_sigmoid`/`double_sigmoid` so the loop/AUC always see maximize-in-[0,1]. Don't thread
  loop `direction` for composed objectives.
- **Budget is per-candidate (OD-2):** one objective eval = one unique call regardless of term
  count. `mol_buffer` dedup already enforces this; keep it when constraints add pre-filtering.
- **`/objective/validate` scores PMO terms via the harness** — keep probe sets tiny (1–2 mols).
- Test basenames unique across the two roots; Alembic revisions chain from `b4ea6a051441`;
  `.gitignore` `oracle/` is now root-anchored (`/oracle/`) — new source dirs are safe.
