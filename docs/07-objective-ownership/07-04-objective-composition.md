# Slice 07-04 — objective composition engine + loop consumption

**Goal:** A run can score against a **composed multi-term objective** — weighted
oracles + transforms → one scalar in [0,1] — launched, run to completion, and badged
`exploratory`. The benchmark path (no objective) stays byte-identical.

## Split note
The plan's Task 07-04 bundled constraints. To keep this ≤2 pages and the loop change
low-risk, **constraints (SMARTS include/exclude + property bands + constraint-
starvation) are split to slice 07-04b**. This slice is the objective engine + loop
consumption + `/objective/validate` + mode enforcement.

## Design
- `packages/core/capychem/objective.py`:
  - `TransformSpec` → transforms mapping a raw oracle value to [0,1]: `identity`
    (passthrough for an already-[0,1] oracle), `sigmoid`, `reverse_sigmoid`,
    `double_sigmoid`/`step` (band), `value_map`. (REINVENT4 parity.)
  - `ObjectiveTerm{oracle, oracle_kwargs, weight, transform}`; `ObjectiveSpec{terms,
    aggregator}` with `weighted_sum`|`weighted_product`. Aggregate of [0,1] terms
    stays in [0,1] **by construction** (preserves AUC comparability).
  - `Objective` resolves each term's oracle from the registry (07-03) and exposes
    `evaluate_async(smiles, *, pmo_scorer)` → `list[ObjectiveResult(score|None,
    cost_usd)]`. **Dependency-injected `pmo_scorer`** = the loop's retry-wrapped
    `score_batch_async`, so a PMO term keeps the exact harness/backend/cost/retry path
    (byte-identical); descriptor terms score sync in a thread, cost 0. A term is
    `None` (candidate unscored) if ANY term is None.
  - `from_json`/`to_json` for `Run.objective_json` (already a column, 07-01).
- **Loop consumption (`loop/graph.py` score node), zero-risk branch:** when
  `state.get("objective_json")` is present, evaluate the composed objective; else the
  **unchanged** benchmark path (same lines). Budget stays per-candidate (OD-2).
  `LoopState`/`RunConfig` gain `objective_json`; `runner._drive` threads it.
- **Route + mode:** `CreateRunRequest.objective_json`; `derive_mode(objective_json=…)`
  ⇒ exploratory; persist to `Run.objective_json`. `POST /objective/validate` previews
  the composite scalar + per-term breakdown on a probe SMILES (and surfaces a bad spec).

## Task checklist (TDD)
- [x] 1. `objective.py` transforms → [0,1] (each transform; identity passthrough). (test)
- [x] 2. `ObjectiveSpec` weighted_sum/product in [0,1]; single identity term == raw
      oracle value. (test)
- [x] 3. `Objective.evaluate_async` with injected `pmo_scorer` + descriptor terms;
      None if any term None; cost = sum of term costs. (test with stub scorer)
- [x] 4. `from_json`/`to_json` round-trip. (test)
- [x] 5. `LoopState`/`RunConfig`/`runner` thread `objective_json`; score-node branch
      (benchmark path unchanged; composed path evaluates objective). (test: gen scores
      via objective; benchmark path untouched)
- [x] 6. `schemas.CreateRunRequest.objective_json` + `derive_mode` ⇒ exploratory +
      persist. (API test)
- [x] 7. `POST /objective/validate` preview endpoint. (API test)
- [x] 8. Gate: mypy · ruff · pytest (incl. benchmark byte-identical) · web unaffected.

## Acceptance
A 2-term composed objective produces a single [0,1] scalar, runs the loop to
completion, and is tagged `exploratory`. A single identity-PMO term equals the raw
oracle. The benchmark (no-objective) path is byte-identical.

## Notes / deferrals
- Constraints (SMARTS + bands + starvation) → 07-04b.
- Frontend objective builder → 07-08 (this slice ships the API + `/objective/validate`).
