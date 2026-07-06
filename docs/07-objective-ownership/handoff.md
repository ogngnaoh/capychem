# Handoff — milestone 07 objective-ownership

## Next session start here
Branch off `main` (branch-first), then execute slice **07-05 quality & trust layer**
(plan Task 07-05) — the headline reward-hacking defense that ships WITH the now-landed
pluggable seam. Build:
1. `packages/core/capychem/quality.py` — per-candidate SA-score/QED/Lipinski/Veber/PAINS/
   Brenk, computed at persistence time (bounded cost; all RDKit-native — reuse the 07-03
   descriptor oracles + 07-04b `Constraints`/FilterCatalog where possible).
2. Alembic revision (chain from head `ed2d80a8ccda`): `Candidate` quality fields (or a
   linked `CandidateQuality`).
3. `loop/graph.py` persist path — attach quality to each persisted Candidate;
   `logic.build_summary` — run-level MOSES internal diversity (mean pairwise Tanimoto on
   Morgan FPs) + novelty vs seed into `summary_json` (JSON, no migration).
4. `packages/core/capychem/trust/gates.py` — **de-dup `_PARSE_RATE_FLOOR`** (currently
   duplicated in `eval/verdict.py:22` + `eval/beat.py:22`) + `valid_smiles_gate` into one
   home; add the custom-oracle **canary** (score a fixed degenerate probe set before an
   exploratory run on a new oracle; warn on implausibly-high scores) and the **OD-4 gate**
   (annotate-only in benchmark — top-10 stays comparable; per-run hard-drop toggle allowed
   only in exploratory mode).
5. `apps/web/components/workbench/ui.tsx` — quality badges on top-K tiles; diversity/novelty
   in the run summary. Tests: `test_quality.py`, `test_trust_gates.py`.

Then 07-06 (manifest) → 07-07 (export) → 07-08 (UI), per milestone.md + the plan.

## Current state
- Slice **07-04b shipped** (merged to `main`): hard constraints. New
  `packages/core/capychem/constraints.py` (`Constraints.from_json`/`passes` — RDKit
  `FilterCatalog` PAINS/BRENK/NIH + custom SMARTS include/exclude; invalid→False). Score
  node drops constraint-failing candidates before scoring (no budget spent); a fully-failed
  generation is flagged `_constraint_starved`; `stop_check` accumulates the streak and
  `stop_reason` terminates as **`constraint_starved`** at streak ≥ `plateau_window` (distinct
  from plateau/no_progress — a starved gen never fires no_progress). `constraints_json`
  threaded through config/runner/route; `derive_mode(constraints_json=…)` ⇒ exploratory.
  Soft property bands need **no new code** (a band = a descriptor-oracle objective term with
  a `double_sigmoid` transform, 07-04).
- **Alembic head `ed2d80a8ccda`**: `runs.status` widened `String(16)`→`String(32)` (dev DB
  upgraded) because `constraint_starved` is 18 chars. New revisions chain from this head.
- Gate all green: mypy (61 files) · ruff · **377** backend (+15) · migration drift · web untouched.
- `main` ahead of `origin/main` (unpushed) + m07-02/03/04/04b commits.

## Active concerns
- **Benchmark byte-identical:** the score node's constraint filter + `_constraint_starved`
  are inert when `constraints_json` is None (streak stays 0, stop_reason unchanged). Keep it.
- **Starvation-vs-empty-population limitation:** if constraints starve gen 0 *entirely*, the
  survivor population empties, so the next generation proposes nothing (candidates empty ⇒
  `_constraint_starved=False`) and the run terminates as `no_progress`, not `constraint_starved`.
  The distinct signal reliably fires when candidates persist but keep failing for a full
  window. Unit-proven; a full-loop starvation e2e is fragile, so not added. Documented in log.
- **07-05 trust gate is OD-4:** annotate-only in benchmark (top-10 comparability preserved);
  hard-drop toggle exploratory-only. Don't let a quality gate change the benchmark top-10.
- Test basenames unique across the two roots; `.gitignore` `oracle/` is root-anchored.
