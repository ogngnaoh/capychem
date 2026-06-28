# Slice 02 — plateau-stop-and-signal

> Milestone 02 (`end-to-end-loop`). Status: **in-progress** (LAST slice in m02). Deps: none.
> Design: `docs/superpowers/specs/2026-06-28-plateau-stop-and-signal-design.md`.
> Plan: `docs/superpowers/plans/2026-06-28-plateau-stop-and-signal.md`.

## Goal

Enforce FR-003 — when the top-10 mean score has not improved for the configured
`plateau_window` consecutive generations, the product/CLI loop stops with a
`plateaued` status — and surface a distinct plateau signal in watch-live (Story 2;
milestone exit criterion 6). Completing this closes milestone 02.

## Plan

- **Pure logic** (`loop/logic.py`): `is_plateau(top10_history, plateau_window)` +
  `PLATEAU_MIN_IMPROVEMENT=1e-9`; `stop_reason` gains `top10_history`/`plateau_window`
  kwargs, priority `exhausted > plateaued > max_generations > no_progress`.
- **Node wiring** (`loop/graph.py` `stop_check`): pass the `auc_curve` y-values +
  `state["plateau_window"]` into `stop_reason`. Shared by API + CLI; `eval/` untouched.
- **Status propagation:** generic — `"plateaued"` rides the existing
  `stop_reason → status → run.complete` path. No new WS event, no DB migration
  (`String(16)` fits).
- **Snapshot** (`schemas.py`, `runner.py`, `routes_runs.py`): add `plateau_window`
  to `RunSnapshot` (live path from `cfg`, DB path from `row`) so the signal copy
  names the window.
- **Frontend** (`lib/plateau.ts` new, `lib/api.ts`, `LiveRun.tsx`): pure
  `plateauNotice` helper; `"plateaued"` added to `TERMINAL`; amber callout rendered
  in watch-live.
- **Testing:** pytest (`is_plateau`, `stop_reason` priority, `stop_check` node);
  vitest (`plateauNotice`, `runEvents` plateaued status). Full gate + manual live
  plateau check.

## Tasks

- [ ] Task 1 — Plateau pure logic (`is_plateau` + `stop_reason` integration) + tests
- [ ] Task 2 — Wire `stop_check` to feed the curve + `plateau_window` + node test
- [ ] Task 3 — Expose `plateau_window` on `RunSnapshot` (live + DB paths) + test
- [ ] Task 4 — Frontend plateau signal (`plateauNotice` + `LiveRun` callout) + tests
- [ ] Task 5 — Full gate (pytest · mypy · ruff · vitest · web typecheck/lint) + live check

## Notes

- **Monotonicity** makes plateau detection trivial and robust: the elitist survivor
  pool means `top10_mean` never decreases, so "no improvement" is exactly "flat".
- **Scope guard:** `packages/core/eval/` has its own loop and does NOT call
  `stop_check` — slice 06's beat verdict cannot regress. Verified by grep.
- **Deferred:** configurable plateau *improvement threshold* (PRD open-question);
  this slice ships the `plateau_window` knob with a fixed ε.
- **`plateaued` vs `no_progress`:** complementary — `no_progress` fires on a single
  generation that scored nothing; `plateaued` needs a full window of scored-but-flat
  generations.
