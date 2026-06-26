# Handoff — 02-end-to-end-loop (slice 04 shipped + merged; next = slice 05)

## Completed this session

- **Shipped slice 04 `llm-proposer-with-ga-fallback`** (milestone 02's heaviest slice) via
  subagent-driven TDD: brainstorm → design spec → plan → 8 tasks (each implementer + task review) →
  whole-branch review → **merged to `main` (fast-forward `1948379 → ecfab36`)**. Implementation commits
  `fd549c3..db3597b` (+ design `c6b4f71`, plan/slice-doc `9306a8b`, ship-docs `ecfab36`).
- Landed: shared `loop/strategy.py`; a new `fallback` graph node (`propose→validate→fallback→score→
  persist→stop_check`, keeping the frozen `valid_smiles` stat LLM-only); per-candidate provenance
  (`Generation.proposer_used="mixed"`); `mutation_strategy` threaded launch→`RunConfig`→`LoopState`
  (+ API schema, both CLIs); observational >80% gate; headless `run_reproduction(llm)`. Review caught
  + fixed two real bugs (stale `_fallback_validated` re-scoring; a frozen-`proposer.py` edit reverted).
- Gate green: **pytest 98 passed**, mypy strict clean, ruff clean. `proposer.py`/`harness` untouched.

## Slice status across milestone

- `01-launch-and-watch-jnk3` → planned
- `02-plateau-stop-and-signal` → planned
- `03-modal-llm-propose-endpoint` → shipped + real-API confirmed — frozen
- `04-llm-proposer-with-ga-fallback` → **shipped 2026-06-26 — frozen**
- `05-unique-call-budget-and-cost-ledger` → planned (next)
- `06-beat-graph-ga-on-jnk3` → planned

Build order: `01 ∥ 02 ∥ 03 → 04 → 05 → 06`.

## Current state

- `main` @ `ecfab36` (slice 04 merged). **`main` is 16 commits ahead of `origin/main` and UNPUSHED**
  (local-only by choice) — push when ready. Feature branch deleted; working tree clean.
- `mutation_strategy` defaults to `"graph_ga"` everywhere → existing graph_ga product + eval paths unchanged.
- Infra (m01): Langfuse v2 :3001, Postgres :5432, `CAPYCHEM_ORACLE_BACKEND` unset (local harness).

## Next session start here

**Start slice 05 `unique-call-budget-and-cost-ledger`** (deps 03, 04). Literal first action: read
`docs/02-end-to-end-loop/milestone.md` (Scope + the "Cost / budget" integration note) + this handoff,
then begin the slice-05 brainstorm → spec → plan → TDD loop. Slice 05: memoize/dedup oracle calls by
canonical SMILES so budget counts unique calls; populate `RunCost.llm_cost_usd`; rewire the per-gen cost
gate to read `total_usd`. (Slices 01 & 02 are dependency-free and can slot in anytime. Push `main` first
if you want origin current.)

## Active concerns

- **Gate purity (slice-06 BLOCKER):** `summary_json.valid_smiles.rate` includes the gen-0 seed pop
  (always valid), so it isn't purely LLM validity. Make it LLM-only (exclude the `"starting"` generation
  / filter `proposer=="llm"`) BEFORE slice 06 reads the ≥80% jnk3 verdict. (In milestone notes + slice doc.)
- **`llm:propose` span (slice-05 nicety):** static params only, opens after the await — enrich with
  token/cost + wrap the await when the `RunCost.llm_cost_usd` ledger lands.
- **Product vs headless budget differ** (product counts every scored call; headless memoizes unique) —
  slice 05 unifies; G6 still holds (headless eval is authoritative AUC).
- **Modal `propose()` `n=1` latent bug** deferred (no Modal access); mirror the proposer fan-out if Modal returns.

## Slice log

- 2026-06-26 — Slice 03 (`modal-llm-propose-endpoint`) fully closed (real-API smoke, `8928f59`).
- 2026-06-26 — Slice 04 (`llm-proposer-with-ga-fallback`) shipped + merged to `main` (`fd549c3..db3597b`, ship `ecfab36`).
