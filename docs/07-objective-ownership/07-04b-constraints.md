# Slice 07-04b — hard constraints + constraint-starvation

**Goal:** A run can carry **hard structural constraints** (SMARTS include/exclude +
PAINS/Brenk catalogs) applied at the validity gate, and surfaces a distinct
**constraint-starvation** signal when nothing can satisfy them — separate from the
FR-003 plateau. Benchmark path untouched.

## Design
- `packages/core/capychem/constraints.py`:
  - `Constraints.from_json({catalogs, smarts_exclude, smarts_include})` — RDKit
    `FilterCatalog` for `PAINS`/`BRENK`, plus custom `MolFromSmarts` exclude/include.
  - `passes(smiles) -> bool` — True iff the molecule matches NO exclude/catalog alarm
    AND matches EVERY required include. Invalid SMILES → False (never trusted).
- **Property bands are NOT new code** — a soft MW/logP/TPSA band is just an objective
  term (`oracle: mw|clogp|tpsa` + `double_sigmoid` transform), already supported by
  07-04. Documented, not reimplemented.
- **Validity-gate application (score node):** when `constraints_json` is present, filter
  the batch to constraint-passing candidates *before* scoring (constraint-failing = like
  invalid: dropped, no budget spent). A generation whose candidates were all dropped by
  constraints is **starved**.
- **Starvation ≠ plateau/no_progress:** the score node returns `_constraint_starved`;
  `stop_check` tracks a streak. `stop_reason` gains a branch: a starved generation never
  fires `no_progress` (the GA keeps proposing new molecules); only a streak ≥
  `plateau_window` terminates as **`constraint_starved`**. Plateau/no_progress apply only
  to non-starved generations.
- **Wiring:** `constraints_json` through `RunConfig`/`LoopState`/`runner`;
  `CreateRunRequest.constraints_json` + validator; `derive_mode(constraints_json=…)` ⇒
  exploratory; persist to `Run.constraints_json` (07-01 column).

## Task checklist (TDD)
- [x] 1. `constraints.py` `Constraints.from_json`/`passes` — SMARTS exclude/include +
      PAINS/Brenk; invalid → False. (test)
- [x] 2. `stop_reason` constraint-starvation branch (starved gen ≠ no_progress; streak ≥
      window ⇒ `constraint_starved`). (logic test)
- [x] 3. Score node filters batch by constraints; returns `_constraint_starved`;
      `stop_check` threads the streak. `LoopState` keys. (test)
- [x] 4. `RunConfig`/`runner` thread `constraints_json`. `schemas.CreateRunRequest`
      + validator; `derive_mode` ⇒ exploratory + persist. (API test)
- [x] 5. Gate: mypy · ruff · pytest (benchmark byte-identical) · web unaffected.

## Acceptance
A SMARTS-exclude constraint drops matching molecules before scoring; a run that can
never satisfy its constraints terminates as `constraint_starved` (not `plateaued`/
`no_progress`); the benchmark (no-constraint) path is byte-identical.

## Notes / deferrals
- Constraints UI (pattern entry + preview) → 07-08.
- Soft bands need no code (objective `double_sigmoid` term).
