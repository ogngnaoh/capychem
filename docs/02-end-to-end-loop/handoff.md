# Handoff — 02-end-to-end-loop (slice 04 shipped; next = slice 05)

## Completed this session

- **Shipped slice 04 `llm-proposer-with-ga-fallback`** (the heaviest slice) via subagent-driven TDD:
  brainstorm → design spec → plan → 8 tasks, each with a fresh implementer + a task review, then a
  whole-branch review. Branch `slice-04-llm-proposer-ga-fallback`, 12 code commits `fd549c3..db3597b`
  (+ design `c6b4f71`, plan/slice-doc `9306a8b`).
- Landed: shared `loop/strategy.py` (prompt / async LLM call / `propose_llm_sync` bridge / `ga_fill` /
  `fallback_fill`); a new `fallback` graph node (`propose→validate→fallback→score→persist→stop_check`)
  so the frozen `valid_smiles` stat stays LLM-only; per-candidate `ValidCandidate.proposer` provenance
  (`Generation.proposer_used="mixed"`); `mutation_strategy` threaded launch→`RunConfig`→`LoopState`
  (+ API schema, both CLIs); observational >80% `valid_smiles_gate`; headless `run_reproduction(llm)`.
- Review caught + fixed two real bugs: a multi-gen **stale `_fallback_validated`** re-scoring bug
  (`d8f1c88`) and a **frozen-`proposer.py` edit** that was reverted, moving the unique-stub invariant
  into the e2e (`33427a5`).
- Gate green: **pytest 98 passed**, mypy strict clean (30 files), ruff clean. `proposer.py` byte-identical
  to base (frozen, untouched).

## Slice status across milestone

- `01-launch-and-watch-jnk3` → planned
- `02-plateau-stop-and-signal` → planned
- `03-modal-llm-propose-endpoint` → shipped + real-API confirmed — frozen
- `04-llm-proposer-with-ga-fallback` → **shipped 2026-06-26 — frozen**
- `05-unique-call-budget-and-cost-ledger` → planned (next)
- `06-beat-graph-ga-on-jnk3` → planned

Build order: `01 ∥ 02 ∥ 03 → 04 → 05 → 06`.

## Current state

- Branch `slice-04-llm-proposer-ga-fallback` is gate-green and **awaiting the merge decision** (not yet
  merged to `main`; `main` @ `1948379`). Working tree clean.
- `mutation_strategy` defaults to `"graph_ga"` everywhere → existing graph_ga product + eval paths unchanged.
- Carried infra (m01): Langfuse v2 :3001, Postgres :5432, `CAPYCHEM_ORACLE_BACKEND` unset (local harness).

## Next session start here

**Merge slice 04 to `main`**, then **start slice 05 `unique-call-budget-and-cost-ledger`** (deps 03,04):
memoize oracle calls by canonical SMILES so budget counts unique calls; populate `RunCost.llm_cost_usd`;
rewire the per-gen cost gate to read `total_usd`. Slices 01 & 02 are dependency-free and can slot in anytime.

## Active concerns

- **Gate purity (slice-06 BLOCKER):** `summary_json.valid_smiles.rate` accumulates the gen-0 seed pop
  (always valid), so it is NOT purely LLM validity. Bounded on stub runs, but **make it LLM-only**
  (exclude the `"starting"` generation / filter `proposer=="llm"`) BEFORE slice 06 reads the ≥80% jnk3
  verdict. (Recorded in milestone integration notes + the slice doc.)
- **`llm:propose` span (slice-05 nicety):** carries static params only and opens after the await; enrich
  with token/cost + wrap the await when the `RunCost.llm_cost_usd` ledger lands.
- **Product vs headless budget semantics differ** (product counts every scored call; headless memoizes
  unique) — slice 05 unifies; G6 still holds (headless eval is the authoritative AUC).
- **Modal worker `propose()` `n=1` latent bug** still deferred (no Modal access); mirror the proposer fan-out if Modal returns.

## Slice log

- 2026-06-16 — Milestone 02 scoped (agent-team planning; 6 slices).
- 2026-06-18 — Slice 03 shipped; 2026-06-26 — Slice 03 fully closed (real-API smoke, commit `8928f59`).
- 2026-06-26 — **Slice 04 shipped:** LLM proposer + Graph-GA fallback, subagent-driven TDD; whole-branch
  review (no Critical, 1 Important deferred to s06); pytest 98; commits `fd549c3..db3597b`.
