# Slice 02 — langfuse-end-to-end

> Status: **shipped (2026-06-16)** — FROZEN. Track B. Merge `5d05c18`; impl `8a7fac9`,`c12ed78`,`725a51f`,`154a0e0`,`b837d56`.
> Design spec: `docs/superpowers/specs/2026-06-15-langfuse-end-to-end-design.md`
> Implementation plan: `docs/superpowers/plans/2026-06-15-langfuse-end-to-end.md`

## Goal

Make FR-014 real: auto-load `.env.local`, add the missing per-generation span so the Langfuse trace is a true **run→generation→node** hierarchy, and verify a real nested trace is viewable in the UI.

## Plan

The walking skeleton already wired per-node spans, the run-level trace, and `flush()`. Three gaps to close:
- `capychem/env.py` (new) — idempotent `load_dotenv` of `.env.local`; add `python-dotenv` dep; wire at `capychem-run` CLI + FastAPI lifespan. (Eval CLI intentionally NOT wired — decouples from slice 1; it needs no Langfuse/env.)
- `trace.py` — `span()` gains `parent_observation_id` (v2 observation-nesting); add `gen_span`/`end_gen_span` + an in-process registry (gen span must survive across the 5 separate LangGraph node calls).
- `state.py`/`graph.py`/`cli.py`/`runner.py` — thread `run_trace_id` (the trace) distinct from `gen_span_id` (current generation span); open the gen span in `propose`, end it in `stop_check`; nodes nest under it. Lightweight metadata only (`gen_index`, counts, `best_score`, `calls_used`).

**Constraints:** tracing never breaks the loop (helpers stay exception-safe); keys in `.env.local` / env only — never commit (SPEC §8.1).

**Testing:** mock-client unit tests (loader idempotent; `parent_observation_id` threading; gen-span lifecycle); harness/DB-free node-level nesting test (gen-0 `propose` is a pure file read); orchestrator runs a real loop, fetches the trace via the Langfuse API to assert nesting, + a manual UI screenshot.

## Tasks

- [x] Task 1 — `env.py` loader + `python-dotenv` dep + tests
- [x] Task 2 — wire `load_local_env` at `capychem-run` CLI + FastAPI lifespan
- [x] Task 3 — `trace.py` `parent_observation_id` (confirmed first-class in langfuse 2.60.10) + `gen_span`/`end_gen_span` registry + tests
- [x] Task 4 — thread `run_trace_id`/`gen_span_id`; open/close gen span in `graph.py`; update `cli.py` + `runner.py` + nesting test
- [x] Task 5 — real-key verification: traced loop (run 259) → Langfuse-API assertion run→generation:0–4→node:5, **0 orphans**; trace `0fc85490-…` viewable at `:3001`
- [x] Gate — `pytest` 57 passed · `mypy` clean · `ruff` clean (integrated tree, real output)
- [x] Reviews — spec-compliance APPROVE + code-quality (gen-span leak found→fixed `b837d56` + 2 regression tests) + integration APPROVE-FOR-MERGE

## Notes

- **Verify before building:** confirm `parent_observation_id` is accepted by `langfuse 2.60.10`; fallback is v2 stateful chaining (`trace.span().span()`), which pairs cleanly with the live-handle registry.
- Prereqs DONE (per handoff): Langfuse v2 self-hosted on `:3001`, real keys in `.env.local` authenticate (SDK 2.60.10, `auth_check` True). The keys only load via shell export until Task 1/2 land the dotenv wiring.
- Worktree note: this slice's unit tests are mock-based (harness-free). Run Task 5's real-loop verification from the MAIN checkout (needs the harness venv + loaded `.env.local`), not the worktree.
- Gen-span lifecycle uses an in-process registry, NOT a graph→subgraph refactor (scope).
