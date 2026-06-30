# Slice 03 — analyzer-live-surface

> Milestone 03 `analyzer-and-scale` (SPEC Phase 3). The **last remaining** slice — shipping it completes the
> milestone. Deps: 01 ✓ (persists `AnalyzerHypothesis` rows). **Surface-only: no analyzer logic, no eval,
> no LLM/oracle spend.**
> Design: `docs/superpowers/specs/2026-06-29-analyzer-live-surface-design.md` ·
> Plan: `docs/superpowers/plans/2026-06-29-analyzer-live-surface.md`.

## Goal

Surface the analyzer's per-generation hypotheses to the operator — live over the run WebSocket as each is
formed, and as a full per-generation sequence in the run view — satisfying FR-009 / FR-011, Story 2/3, and
milestone exit criterion #7.

## Plan

- **Core (`packages/core`):** the loop accumulates a surface-ready `HypothesisRecord`
  (`{after_generation_index, text, structured_json}`) into a new `state["analyzer_hypotheses"]` list in the
  `_analyze` node — mirroring how `auc_curve` is accumulated *for observation*. The loop never touches the
  WS layer.
- **WS event (`apps/api`):** `AnalyzerHypothesisOut` + `AnalyzerHypothesisEvent` schemas; the runner
  *observes* `analyzer_hypotheses` growth in its `astream` loop and broadcasts `analyzer.hypothesis`
  (`{after_generation_index, text, structured_json}`) — exactly the `generation.complete` / `auc_curve`
  pattern; the `RunHandle` is **not** threaded into `packages/core`.
- **REST (`apps/api`):** add `hypotheses: list[AnalyzerHypothesisOut]` to `RunSnapshot`, populated by one
  indexed `_hypotheses_for` query (`ix_analyzerhyp_run_after`) in both `GET /runs/{id}` branches — the
  durable rows are the source for a reloaded/completed run (WS replays only the terminal event).
- **Web (`apps/web`):** `RunEvent` union + `applyEvent` gain an `analyzer.hypothesis` case (append /
  replace-by-index, sorted, pure); a new pure `HypothesisSection` renders the **unified "Analyzer
  reasoning"** section below the AUC chart / top-K table — newest-first, latest expanded, focus/avoid chips,
  empty → nothing; wired into `LiveRun`. Hoist the carried-in `plateauNotice` double-call.
- **Testing:** TDD per task — core accumulation (`test_loop_analyze.py`); fast FakeGraph runner broadcast
  (`test_runner.py`); `_hypotheses_for` unit + GA-empty + LLM-stub end-to-end (`test_api.py`); reducer
  append/dedup/purity (`runEvents.test.ts`); component render + empty (`HypothesisSection.test.tsx`). All
  on **stub** backends — no `direct`, no spend.

## Tasks

- [ ] T1 — Core: `HypothesisRecord` + `analyzer_hypotheses` accumulation in `_analyze` (`state.py`, `graph.py`).
- [ ] T2 — API: `analyzer.hypothesis` event schema + runner observe-and-broadcast (`schemas.py`, `runner.py`).
- [ ] T3 — API: `RunSnapshot.hypotheses` + `_hypotheses_for` query wired into both GET branches (`routes_runs.py`).
- [ ] T4 — Web: `AnalyzerHypothesis` type + `applyEvent` `analyzer.hypothesis` case (`api.ts`, `runEvents.ts`).
- [ ] T5 — Web: unified `HypothesisSection` + `LiveRun` wiring + `plateauNotice` hoist.
- [ ] Final — full gates (pytest, mypy both `-p`, ruff; vitest, tsc, eslint) + manual live acceptance (no spend); then ship docs (milestone/handoff flip, freeze, log) → milestone 03 complete.

## Notes

- **`avoid` is `list[str]`** (not a string) and `structured_json` may be `null` (neutral / "no new signal"
  fallback) — both rendered/handled. [[project_deepseek_v4_reasoning_default]] context: analyzer is
  reasoning-OFF, so `structured_json` is reliably parseable post-slice-06.
- **Watch-live and run-detail are the same `LiveRun` component** today — one unified section serves both
  Story 2 (latest) and Story 3 (sequence); operator chose unified over a split callout+timeline.
- **Decoupling is load-bearing:** the Explore agent's suggestion to broadcast from the core `_analyze` node
  (threading the API `RunHandle` in) was rejected — it breaks the runner's "observe only" contract.
- **Out of scope / deferred:** compare-runs (Story 4 / m04); the two legacy-harness follow-ups (median2
  GA-crossover `IndexError`; sitagliptin_mpo oracle NaN) — unrelated hardening, not this slice.
- DeepSeek balance ≈ $2.91 — untouched (no spend this slice).
