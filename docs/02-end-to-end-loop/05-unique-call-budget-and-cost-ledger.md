# Slice 05 — unique-call-budget-and-cost-ledger

> Milestone 02 (end-to-end-loop), SPEC Phase 2. Deps: slices 03, 04 (shipped + frozen).
> Design spec: `docs/superpowers/specs/2026-06-26-unique-call-budget-and-cost-ledger-design.md`
> Plan: `docs/superpowers/plans/2026-06-26-unique-call-budget-and-cost-ledger.md`

## Goal

The product loop counts **unique** oracle calls (cross-gen repeats are cache hits — not
re-scored, not counted, not persisted), `RunCost.total_usd` sums llm + oracle, the ~$50 cost
gate fires on LLM spend alone, and the `llm:propose` span carries token/cost. Demonstrated on
the cheap CPU oracle ("designed-for-expensive, shown-on-cheap"). Satisfies milestone exit
criteria 4 + 5.

## Plan

Five surgical TDD changes (see the plan for per-step code):

- `cost.py` — `record_oracle_cost` gains `llm_usd=0.0`; `total_usd = oracle + llm`.
- `loop/trace.py` — `_live_spans` registry + `update_span()` (yield contract unchanged).
- `loop/state.py` — `LoopState` gains `mol_buffer: set[str]` + `llm_cost_usd: float`.
- `loop/graph.py` — `score` node memoizes unique calls (in-memory `set`, mirrors the
  already-memoized headless `eval/runner.py`); `propose` node accumulates LLM cost + wraps the
  `llm:propose` await with token/cost.
- `apps/api .../runner.py` — per-gen cost gate reads `total_usd` (oracle + llm).

Testing: `test_loop_memoize.py` (new) for the score node; additions to `test_cost.py`,
`test_trace.py`, `test_loop_propose.py`, `apps/api/tests/test_cost_gate.py`. Gate-green
(`uv run pytest` · `mypy -p capychem -p capychem.api` · `ruff check .`) before merge.

## Tasks

- [ ] Task 1 — `record_oracle_cost` records llm + oracle (`total_usd` sums both).
- [ ] Task 2 — `trace._live_spans` registry + `update_span`.
- [ ] Task 3 — `score` node memoization; `LoopState.mol_buffer`; drop orphaned `trim_to_budget` import.
- [ ] Task 4 — `propose` node LLM-cost accumulation + `llm:propose` span enrichment; `LoopState.llm_cost_usd`.
- [ ] Task 5 — API runner cost gate reads `total_usd`.
- [ ] Task 6 — full gate-green verification (`pytest` · `mypy` · `ruff`).

## Notes / decisions

- **Cache hits skipped entirely** (chosen): no re-score, no count, no new `Candidate`/`OracleCall`.
  Invariant: `#OracleCall == calls_used == unique calls`. Consequence: cross-gen repeats never
  reach persistence or the population merge → a `set[str]` memo suffices (no score-cache dict).
- **Memo is in-memory in `LoopState`** (one in-process asyncio task per run); no DB-dedup, no
  resumability this milestone. Headless `eval/runner.py` is **not** modified — already memoizes.
- **`record_oracle_cost` keeps its name** (additive `llm_usd=0.0`) — surgical, keeps the existing
  positional-call test green.
- **`span()`'s `str | None` yield is a tested contract** → enrichment via `_live_spans` + `update_span`,
  not a handle.

## Out of scope / deferred

- **valid_smiles gate purity** (gen-0 seeds inflate the rate) — **slice-06 BLOCKER**; `validate.py`
  / `_validation_stats` untouched here.
- Analyzer (m03), beat-Graph-GA verdict run (slice 06), jnk3 launch/UI (slice 01), plateau-stop
  (slice 02), expensive oracles (stretch).
