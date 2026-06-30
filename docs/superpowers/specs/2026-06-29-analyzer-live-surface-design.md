# Design — analyzer-live-surface (milestone 03, slice 03)

**Status:** approved-for-planning · **Date:** 2026-06-29 · **Author:** session
**Milestone:** `03-analyzer-and-scale` (SPEC Phase 3) · **Slice:** `03-analyzer-live-surface`
**Deps:** slice 01 `analyzer-agent` ✓ (persists `AnalyzerHypothesis` rows + `Generation.analyzer_hypothesis_id`)
**Satisfies:** FR-009 (live push) · FR-011 (run-detail hypothesis sequence) · Story 2 (watch-live latest) · Story 3 (browse) · milestone exit criterion #7.

## 1. Goal

Surface the analyzer's per-generation hypotheses — the closed-loop differentiator MOLLEO lacks — to
the operator, live and after the fact. One sentence: **broadcast each new hypothesis over the run's
WebSocket as it is formed, and render the full per-generation hypothesis sequence (latest emphasized)
in the run view.** This is the *last remaining* milestone-03 slice; shipping it completes the milestone.

Engine-only work (forming/persisting/conditioning the hypothesis) shipped in slices 01/06. This slice is
**surface-only**: no analyzer logic, no eval, no LLM/oracle spend. It touches the WS event layer, one
REST field, and the `LiveRun` web component.

## 2. What already exists (load-bearing context)

- **`_analyze` node** (`packages/core/.../loop/graph.py`, gen ≥1 & `mutation_strategy=="llm"`) forms the
  `{focus, avoid}` hypothesis, persists an `AnalyzerHypothesis` row (`text`, `structured_json`,
  `after_generation_index`, tokens, cost), links `Generation.analyzer_hypothesis_id`, and returns
  `{"analyzer_hypothesis": effective, ...}` into loop state.
- **Runner is a pure observer** (`apps/api/.../runner.py`). Its docstring: *"The loop code itself is never
  modified — we only observe it."* `generation.complete` is broadcast from the `async for state in stream`
  loop by watching `len(state["auc_curve"])` grow (`runner.py:176`). The core loop has **zero** knowledge
  of the WS layer — this decoupling is the contract we preserve.
- **WS endpoint** (`ws_runs.py`) subscribes to a per-run asyncio.Queue and replays only the **terminal**
  `run.complete` event to late subscribers (no per-event replay).
- **`GET /runs/{id}` → `RunSnapshot`** returns top-K / AUC curve / cost from the in-memory snapshot (live)
  or `summary_json` (DB). **No hypotheses today.**
- **Frontend:** run-detail page (`app/runs/[id]/page.tsx`) renders `<LiveRun>` — watch-live and run-detail
  are the *same component*. `LiveRun` fetches the initial `RunSnapshot` via REST then folds WS events via
  the pure `applyEvent` reducer (`lib/runEvents.ts`). WS event types live in `lib/runEvents.ts`; the
  snapshot type in `lib/api.ts`.
- The analyzer runs on **LLM runs only**; Graph-GA runs and gen 0 have **no** hypothesis → empty-state is a
  first-class case, not an error.

## 3. Design

### 3.1 WebSocket event (live push, FR-009)

New event `analyzer.hypothesis`, payload per SPEC §6.3: `{after_generation_index, text, structured_json}`.

- **Pydantic** `AnalyzerHypothesisEvent` in `apps/api/.../schemas.py` (`type: Literal["analyzer.hypothesis"]`).
- **Accumulate, then observe.** The `_analyze` node appends a record
  `{after_generation_index, text, structured_json}` to a new loop-state list `analyzer_hypotheses`
  (typed in `LoopState`). This mirrors exactly how `auc_curve` is accumulated *by the loop* purely so the
  runner can observe it. The single `analyzer_hypothesis` state value (used for prompt conditioning) is
  unchanged; the list is additive and observation-only.
- **Broadcast from the runner**, not the core. In `_drive`'s stream loop, a sibling observation to the
  curve-growth branch: `if len(state.get("analyzer_hypotheses", [])) > last_hyp_len:` broadcast each new
  record as `AnalyzerHypothesisEvent(**record).model_dump()` and advance `last_hyp_len`. No `RunHandle` is
  threaded into `packages/core`; the observer contract holds.
- **Non-terminal** → no `terminal_event` storage and no replay logic. A reconnecting client re-reads the
  full sequence from REST (§3.2).
- **Timing:** the hypothesis state-emission lands *after* that generation's `persist` (so after
  `generation.complete`). A run that breaks at a persist boundary (cost-cap / cooperative stop) before its
  `analyze` runs simply has no hypothesis for that generation — consistent with the persisted DB state.

### 3.2 REST: full sequence on `RunSnapshot` (browse, FR-011)

- Add `hypotheses: list[AnalyzerHypothesisOut] = []` to `RunSnapshot` (`schemas.py`), where
  `AnalyzerHypothesisOut = {after_generation_index, text, structured_json}`.
- In `get_run_endpoint`, **always** query `AnalyzerHypothesis` rows for the run ordered by
  `after_generation_index` (uses the existing `ix_analyzerhyp_run_after` index) and attach — in **both** the
  live-snapshot and DB-fallback branches. The DB rows are the single durable source, so live and completed
  runs render identically; a GA run returns `[]` cheaply. (Small refactor: the live branch must open a
  read session it currently skips.)
- This is the authoritative source for the run-detail "full sequence." The WS stream only *adds* live
  arrivals on top of what REST already returned.

### 3.3 Frontend (unified "Analyzer reasoning" section)

Chosen presentation: **one section**, below the AUC chart / top-K table, newest-first, latest expanded.

- **Types** (`lib/api.ts`): add `AnalyzerHypothesisOut` (`structured_json: { focus?: string; avoid?: string }
  | null`) and `hypotheses: AnalyzerHypothesisOut[]` on `RunSnapshot`.
- **Reducer** (`lib/runEvents.ts`): add the `analyzer.hypothesis` variant to the `RunEvent` union; in
  `applyEvent`, **append-or-replace by `after_generation_index`** into `snap.hypotheses` (dedup absorbs the
  GET-vs-subscribe race), returning a new snapshot (stays a pure function). Initialize `hypotheses: []`
  wherever a base snapshot is constructed.
- **Render** (`LiveRun.tsx`): a section that, when `hypotheses.length > 0`, shows entries sorted by
  `after_generation_index` descending — the newest expanded (prose `text` + focus/avoid chips for whichever
  keys are present), older ones in native `<details>`. `structured_json === null` (neutral / "no new
  signal" fallback) → prose only. `hypotheses.length === 0` → render nothing.
- **In-scope cleanup:** hoist the `plateauNotice(...)` double-call (`LiveRun.tsx:124–128`) to a local
  variable (the carried-in deferred Minor — addressed because we're editing the file).

## 4. Alternatives considered

- **WS broadcast — thread `RunHandle` into the core `_analyze` node** (Explore agent's suggestion).
  *Rejected.* Couples `packages/core` to `apps/api`'s WS layer and violates the runner's "observe only"
  contract; `generation.complete` deliberately does not do this.
- **WS broadcast — runner re-queries the DB for new hypotheses at each generation boundary.** *Rejected.*
  The hypothesis for gen N is persisted in N's `analyze`, *after* N's curve-growth boundary, so a
  boundary-time requery surfaces it one generation late — worse live UX. Observing the post-`analyze` state
  emission is realtime.
- **WS broadcast — observe the single `state["analyzer_hypothesis"]` value + derive the index from
  `gen_index`.** *Rejected.* No new state key, but deriving `after_generation_index` relies on node-timing
  and object-identity; the accumulation list carries the index explicitly and mirrors `auc_curve`.
- **Run-detail — replay every hypothesis over WS on connect** instead of REST. *Rejected.* The WS replay
  channel is terminal-only by design; the durable DB rows are the natural source and already exist.
- **Split the live "latest" callout from the historical sequence into two components/sections.**
  *Rejected by the operator* in favor of the unified section (simpler one-list data path; tail = latest).

## 5. Testing

- **Backend `test_runner.py`** — an `mutation_strategy="llm"` run on **stub** proposer + **stub** analyzer
  backends (free, deterministic) broadcasts `analyzer.hypothesis` events in sequence with monotonic
  `after_generation_index` and non-empty `text`; assert ordering relative to `generation.complete`.
- **Backend `test_api.py`** — over WS, an LLM run yields ≥1 `analyzer.hypothesis`; `GET /runs/{id}` returns
  a populated `hypotheses` list (live and after completion); a Graph-GA run returns `hypotheses == []`.
- **Frontend `runEvents.test.ts`** — `applyEvent` appends a hypothesis; a duplicate `after_generation_index`
  replaces rather than duplicates; input snapshot is not mutated.
- **Frontend component test** — the section renders entries on a snapshot with hypotheses, the newest is
  expanded with chips, and `hypotheses: []` renders nothing (mock pattern per `app/page.test.tsx`).
- **Gates:** `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .` ·
  `pnpm --filter web test` · `pnpm --filter web typecheck` · `pnpm --filter web lint`.

## 6. Out of scope / non-goals

- No analyzer logic / prompt / conditioning change (slices 01/06); no eval; **no LLM or oracle spend**.
- No compare-runs view (Story 4 / FR-012) — milestone 04.
- No 2D molecule rendering work (existing top-K surface is untouched).
- The two legacy-harness follow-ups (median2 GA-crossover `IndexError`; sitagliptin_mpo oracle NaN) are
  unrelated hardening — not this slice.
- No headless-eval WS surface — the analyzer node already runs in both paths (slice 01 / G6); only the
  product loop has a WS, so there is no parity gap to close here.

## 7. Edge cases

- Graph-GA run / gen 0 / LLM run before gen 1 → no hypothesis → section hidden, `[]` from REST.
- Malformed/empty/off-topic analyzer output → slice-01 fallback persists last-good/neutral text (possibly
  `structured_json = null`) → surfaced verbatim; the loop never stalls (handled upstream).
- Late WS subscriber on a live run → REST returns the sequence-so-far; the dedup-by-index reducer absorbs a
  hypothesis persisted between the GET and the subscribe.
- Final generation: if `analyze` ran (natural budget exhaustion), its hypothesis is the last state emission
  and is broadcast before the stream ends; if the run broke at a persist boundary first, that generation
  has no hypothesis (consistent everywhere).
