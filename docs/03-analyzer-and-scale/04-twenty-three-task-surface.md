# Slice 04 — twenty-three-task-surface

> Milestone 03 `analyzer-and-scale`, slice 04 (build order `01 → {02 ∥ 03 ∥ 04} → 06 → 05`; deps: none).
> Design: `docs/superpowers/specs/2026-06-29-twenty-three-task-surface-design.md` ·
> Plan: `docs/superpowers/plans/2026-06-29-twenty-three-task-surface.md`.

## Goal

Make every PMO task launchable end-to-end and add a mode-pluggable `capychem-eval --all` sweep runner —
the last remaining dependency (besides 06 ✓) for slice 05's Week-8 sweep. Pure plumbing, **no eval cost**:
a single source-of-truth task registry, all 23 published Graph-GA baselines, the schema + UI widened to the
full surface, and a sweep runner that walks 23 tasks. No harness/oracle/analyzer/proposer behavior change.

## Plan

A single `eval/tasks.py::PMO_TASKS` feeds the baselines dict, the API schema validator, and the sweep's
default task list. A new `eval/sweep.py` orchestrates the **existing** per-task primitives by mode
(`reproduce` / `head_to_head` / `analyzer_verdict`) with per-task error isolation; `cli.py` wires `--all`.
The launch page gains a `<select>` over a static mirror of the 23 names.

- **`eval/tasks.py`** (new) — `PMO_TASKS: tuple[str,...]`, 23 PyTDC oracle names in Table 2 order.
- **`eval/baselines.py`** — extend `GRAPH_GA_AUC_TOP10` to all 23 (verified table; Sum 13.751); generalize
  the jnk3 sanity-only comment to all tasks.
- **`apps/api/.../schemas.py`** — `task: str` + `field_validator` against `PMO_TASKS` (→ 422; FR-015).
  Consequence: `drd2` becomes valid → the "unknown task" test switches to `not_a_real_task`.
- **`eval/sweep.py`** (new, mirrors `beat.py`/`verdict.py`) — `run_sweep(tasks=PMO_TASKS, *, budget, seed,
  mode, …) -> SweepReport`; dispatches each task to the existing primitive; isolates per-task failures;
  aggregates `auc_sum` / `published_sum` (13.751 ref) / `beats`.
- **`eval/cli.py`** — `--all` flag; mode derived from the existing `--head-to-head`/`--analyzer-verdict`
  flags (default `reproduce`); emits a combined JSON report. Single-task paths untouched.
- **`apps/web/app/page.tsx`** — task `<select>` (23, default jnk3), retitle, thread chosen task into
  `createRun` (was hardcoded `"jnk3"`); update `page.test.tsx` + `e2e/launch.spec.ts`.

Testing: TDD per task, all harness-free / cost-free via the established monkeypatch (`run_reproduction` /
`run_head_to_head` / `run_analyzer_verdict` stubbed in the sweep namespace; `run_sweep` stubbed in the CLI;
`createRun` mocked in the web). Gate each task: `uv run pytest` · `uv run mypy -p capychem -p capychem.api`
· `uv run ruff check .`; web: `pnpm --filter web test` · `typecheck` · `lint`.

## Tasks

- [ ] T1 — `eval/tasks.py`: `PMO_TASKS` (23, unique, qed first); 2 tests.
- [ ] T2 — `eval/baselines.py`: all 23 baselines + Sum 13.751; keys==`PMO_TASKS`; 3 tests.
- [ ] T3 — `schemas.py`: `task: str` + `field_validator`; fix `drd2`→`not_a_real_task`; full-surface accept test.
- [ ] T4 — `eval/sweep.py`: `run_sweep` (3 modes, error isolation, summary); 5 tests.
- [ ] T5 — `eval/cli.py`: `--all` wiring (mode from flags); 3 tests; `--task` made optional under `--all`.
- [ ] T6 — `apps/web/app/page.tsx`: task selector (default jnk3) + thread + retitle; web tests + e2e title.
- [ ] T7 — Full gate (pytest, mypy ×2, ruff; web test/typecheck/lint) + ship docs + finish branch.

## Notes

- **Mode-pluggable `--all` (brainstorm decision):** `--all` composes with existing mode flags, so slice 05
  is a flag-flip (`--all --analyzer-verdict`) + a real run, not new plumbing. Slice 04 validates the whole
  aggregation pipeline cheaply (graph_ga `reproduce` + stubs); the real 23-task sweep is slice 05's
  cost-bounded, confirm-before-invoke deliverable — **not run here**.
- **Harness is already task-agnostic** (`Oracle(name=task)` in `harness/.../score.py`) — confirmed; no
  harness change. The 23 names are the exact PyTDC oracle names.
- **Single source of truth:** the registry is `eval/tasks.py::PMO_TASKS`; baselines + schema derive from it.
  The web mirrors the 23 names in a static const (commented), not a `GET /tasks` endpoint (YAGNI; static list).
- **Published baselines are a sanity reference only** — every head-to-head/verdict decision uses our own
  same-seed control ([[project_eval_compute_budget]]).
- **Untouched:** harness, product loop / LangGraph / WS, DB schema, analyzer/proposer behavior, `eval/beat.py`,
  `eval/verdict.py`, `eval/runner.py`, `eval/metric.py` (the sweep only *calls* them).
- **Out of scope / deferred:** the real 23-task sweep + Week-8 ≥3/23 verdict + cost-gate-at-scale (slice 05);
  per-task baseline hints in the UI; `GET /tasks` endpoint; the live WS hypothesis surface (slice 03).
