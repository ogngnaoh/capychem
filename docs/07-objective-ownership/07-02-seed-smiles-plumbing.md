# Slice 07-02 — seed-SMILES plumbing (FR-001)

**Goal:** An operator can bring their own starting compounds. A pasted SMILES list
reaches the gen-0 population; the run is badged `exploratory`; the integer RNG
`seed` (reproducibility contract, G6) is untouched.

## Why this slice
The UI already has a "Seed molecules" field and the intent layer already validates
a single seed — but the value is **dropped** before `createRun`, so it never reaches
the loop (the FR-001 bug). This is the 6-layer fix so the seed survives end to end.

## Design decisions
- **`seed_smiles` is a `list[str]`** (bring-your-own *compounds*, plural), distinct
  from the integer RNG `seed`. Never overload the RNG seed.
- **Gen-0 population** = validated+canonicalized operator seeds (deduped), then
  **topped up from the shipped starting pool** to exactly `pop_size` (truncated if the
  operator gives more). Top-up guarantees ≥2 parents for crossover and gives the GA
  material. (Plan: "GA-filled from the shipped pool or truncated to exactly pop_size".)
- **Authoritative validation is the `/runs` boundary** (a client can POST directly);
  the intent-preview validation is best-effort only.
- **Persist the operator's raw strings** in `Run.seed_smiles` (provenance for 07-07),
  plus `Run.seed_source` (`default`|`custom`). The loop canonicalizes.
- Any non-empty `seed_smiles` ⇒ `mode=exploratory` via `derive_mode(seed_smiles=…)`.
- Frontend stays minimal (per handoff): the existing single field is split into a list
  on submit; the rich SDF/CSV import UI with accepted/rejected is 07-08.

## Task checklist (TDD; red → green per item)
- [x] 1. `loop/seeds.py::build_seed_population(operator_seeds, pop_size)` — canon+dedup
      seeds, top up from shipped pool, truncate to `pop_size`. (core test)
- [x] 2. `loop/state.py` `LoopState` + `seed_smiles: list[str] | None`.
- [x] 3. `loop/graph.py` gen-0 branch: operator seeds present ⇒ build from them, else
      `_load_starting_pop`. (propose-node test)
- [x] 4. `db/models.py` `Run.seed_smiles` (JSON nullable) + `Run.seed_source` (String).
- [x] 5. Alembic revision chained from head `f8342ecfc066`.
- [x] 6. `run.py` `RunConfig` (+ `seed_smiles`, `seed_source`); `create_run` insert. (test)
- [x] 7. `schemas.py` `CreateRunRequest.seed_smiles: list[str] | None` + RDKit field
      validator (reject unparseable, drop empties, `[]`→None). (test)
- [x] 8. `routes_runs.py` create endpoint: thread seed through `derive_mode` + set
      `seed_source`. (API test: valid⇒exploratory/custom; invalid⇒422; none⇒benchmark;
      int seed untouched)
- [x] 9. `runner.py` `_drive` threads `cfg.seed_smiles` into initial LoopState; resume
      RunConfig reads `row.seed_smiles`/`row.seed_source`.
- [x] 10. Frontend: `api.ts` `CreateRunBody.seed_smiles?: string[]`; `Launcher.tsx`
      parse the field to a list + include in `createRun`; guard `resolve()` for multi.
- [x] 11. Gate: mypy · ruff · pytest (core + api) · web typecheck/lint/vitest. Upgrade
      dev DB (`alembic upgrade head`).

## Acceptance
A run launched with a pasted valid SMILES list starts gen-0 from exactly those
molecules (topped-up/truncated to `pop_size`), is tagged `exploratory`, and the
integer RNG-seed reproducibility contract is unaffected. Invalid seed ⇒ 422 at `/runs`.

## Notes / deferrals
- Rich seed-import UI (SDF/CSV upload, accepted/rejected list) → 07-08.
- Surfacing seeds in the run snapshot/export → 07-06/07-07.
