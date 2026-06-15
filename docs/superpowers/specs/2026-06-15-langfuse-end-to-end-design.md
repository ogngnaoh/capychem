# Design — Slice `02-langfuse-end-to-end`

**Date:** 2026-06-15
**Status:** Design approved; pending written-spec review
**Milestone:** `01-harness-reproducibility` (SPEC §9 Phase 1)
**Related:** PRD FR-014 (auditable decision trace) · SPEC §8.3 (observability) · CLAUDE.md critical constraint (never commit keys) · SPEC §8.1

---

## 1. Problem & goal

FR-014 requires every loop decision auditable in an external observability surface (Langfuse). The walking skeleton already wired a lot: `trace.py` (v2 SDK, exception-safe no-op when keys absent), per-**node** spans on all five nodes, a run-level trace in both the CLI and FastAPI paths, and `flush()` on exit. Three gaps remain, and this slice closes them:

1. **No `python-dotenv`** — keys only work if exported into the shell; `.env.local` (gitignored, already provisioned with authenticating keys) is never loaded by code.
2. **The trace is 2-level, not 3.** `cli.py` sets `gen_span_id = run_span_id` and never updates it, so all node spans nest *directly* under the run trace (run→node). The required structure is run→**generation**→node. Compounding this, `trace.span()` nests via `trace_id=parent_id`, which only attaches an observation to the *trace*, never to a parent *span*.
3. **No real-key verification** — tests exercise only the mock/no-op path; nobody has confirmed a real nested trace lands and is viewable.

Exit: a real nested trace (run→generation→node) is viewable in the Langfuse UI for a loop run, FR-014 verified — no longer a no-op.

## 2. Decisions (resolved during brainstorming)

| Fork | Decision | Why |
|---|---|---|
| Trace content richness | **Lightweight structural** — `gen_index`, `#proposed`, `#valid`, `best_score`, `calls_used` | Enough to audit each generation per FR-014; per-candidate SMILES/scores already live in Postgres + the run-detail view; LLM-call richness is moot (no LLM until milestone 02) |
| FR-014 verification | **Programmatic + manual UI** | CI unit tests assert nesting threading (mock); orchestrator runs a real loop, fetches the trace via the Langfuse API to assert run→generation→node, and screenshots the UI for the "viewable" sign-off |
| Gen-span lifecycle across separate LangGraph node calls | **In-process registry** keyed by `(run_id, gen_index)`, ended in `finally` at the generation boundary | Minimal; avoids refactoring the five-node graph into subgraphs |
| 3-level nesting itself | **Required, not optional** | Mandated by the milestone exit criteria + orchestration brief |

## 3. Architecture / changes

### 3.1 `capychem/env.py` (new) — dotenv loader
`load_local_env() -> None`: idempotent `load_dotenv(find_dotenv(".env.local"))` against the repo root. Called at three entrypoints so every traced loop sees the keys: `capychem-run` (`cli.py` `main`), `capychem-eval` (slice-1 CLI `main`), and the FastAPI lifespan startup (`apps/api`). Add `python-dotenv` to `packages/core` `[project.dependencies]`.

### 3.2 `trace.py` — generation span + real observation nesting
- Split the two ids: `span(name, *, trace_id, parent_observation_id=None, **md)` — node spans get `trace_id=run_trace_id` **and** `parent_observation_id=gen_span_id` (Langfuse v2's observation-nesting param).
- Add `gen_span(run_trace_id, gen_index, **md) -> id | None` — opens a generation-level span as a direct child of the run trace (`trace_id=run_trace_id`, no parent observation); registers the live handle in the in-process registry so it can be `.end()`ed at the generation boundary.
- Add `end_gen_span(run_id, gen_index)` (or equivalent) — ends + de-registers the gen span; safe no-op when disabled/missing.
- Keep every helper exception-safe (tracing must never break the loop) — existing invariant.

### 3.3 `state.py` / `graph.py` — open/close the gen span per generation
- LoopState carries `run_trace_id` (the trace id, set once) **distinct from** `gen_span_id` (the current generation span id, updated each generation).
- Open a gen span at generation start (first node of the generation); end it at `stop_check` (generation end), via `finally`, using the registry.
- All five node spans pass `trace_id=run_trace_id, parent_observation_id=gen_span_id` with lightweight metadata.
- Mirror the same threading in the FastAPI `runner.py` `_drive` path.

### 3.4 Verification (orchestrator)
After the unit tests are green, run a small traced loop (e.g. `capychem-run --task qed --budget 60 --pop-size 20 --offspring 10`) with `.env.local` auto-loaded; fetch the trace via the Langfuse SDK/API and assert the observation tree is run→generation→node; capture a manual UI screenshot from `localhost:3001`.

## 4. Testing (SPEC §10)

- **Unit (mock client, CI):** `load_local_env()` is idempotent and finds `.env.local`; node spans thread `parent_observation_id=gen_span_id` + `trace_id=run_trace_id`; a gen span is opened per generation and ended at the boundary (success *and* exception paths, extending the existing `test_trace.py` pattern).
- **Integration (local, keys present — skipped in CI without keys):** a real short loop → fetch trace via Langfuse API → assert run→generation→node observations exist.
- **Manual (orchestrator):** UI screenshot of the nested trace.

## 5. Risks

- **v2 SDK param name** — confirm `parent_observation_id` against the installed `langfuse 2.60.10` (alternative: switch to v2 stateful chaining `trace.span().span()`, which auto-sets the parent and pairs naturally with the registry). Verify before building.
- **Gen-span lifecycle** across async nodes + concurrent runs — registry keyed by `(run_id, gen_index)`; end in `finally`; ensure no leak and that gen spans end *before* `flush()`.
- **Secrets** — keys stay in `.env.local` (gitignored) / env only; never commit (SPEC §8.1). Verification screenshots must not expose secret values.

## 6. Out of scope / deferred

- **LLM-call generation spans** (prompt/completion/tokens/latency) → milestone 02 (no LLM yet).
- **Tracing the eval reproduction runner** (slice 1) → not traced; it's a benchmark, not the agent loop. (`load_local_env()` still runs at the eval CLI for env consistency.)
- **Trace-deletion cascade** (`DELETE /runs/{id}` → Langfuse API) → milestone 04 polish.

## 7. Shared-file coordination

`packages/core/pyproject.toml`: this slice edits `[project.dependencies]` (+`python-dotenv`); slice 1 edits `[project.scripts]` (+`capychem-eval`) — different blocks, trivial merge. This slice's implementer runs **worktree-isolated**, concurrent with slice 1. The worktree gets no own harness venv; harness-backed tests there must set `CAPYCHEM_HARNESS_PYTHON` to the main checkout's `harness/.venv/bin/python` — but note slice 2's tests are mock-based and largely harness-free, so this matters mainly if the real-loop verification runs from the worktree (prefer running that verification from the main checkout).
