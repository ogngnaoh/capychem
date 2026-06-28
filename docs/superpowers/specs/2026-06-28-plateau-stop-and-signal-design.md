# Design — plateau-stop-and-signal (milestone 02, slice 02)

**Status:** approved · **Date:** 2026-06-28 · **FR:** FR-003 · **Story:** US-2
**Milestone:** 02-end-to-end-loop · exit criterion 6 · LAST slice in m02.

## Goal

When the top-10 mean score stops improving for `plateau_window` consecutive
generations, the product/CLI loop terminates with a `plateaued` status, and the
watch-live view surfaces a distinct plateau signal explaining the stop. Satisfies
FR-003 ("System MUST stop a run when the top-K score has not improved for the
configured plateau window"), Story 2 (live view surfaces a plateau signal), and
milestone exit criterion 6.

## Scope boundary

- Touches the **shared LangGraph `stop_check` node** (`loop/graph.py`) +
  `stop_reason` (`loop/logic.py`) → applies to the **API product loop and the CLI**.
- Does **NOT** touch `packages/core/capychem/eval/` — that module has its own loop
  (verified: it does not import `build_graph`/`stop_check`/`stop_reason`). Slice 06's
  shipped beat verdict therefore cannot regress.
- **No new WS event type**, **no DB migration**, **no expensive-oracle work.**

## 1. Plateau definition (pure backend)

The survivor pool is elitist: `merge_and_truncate` keeps the global top `pop_size`
across all generations, so `top10_mean` (the `auc_curve` y-value) is
**monotonically non-decreasing**. "Not improved" therefore means *flat* (Δ ≤ ε)
across the window — there is no transient-dip case to handle.

New pure helper in `loop/logic.py`:

```python
PLATEAU_MIN_IMPROVEMENT = 1e-9  # float-noise guard; given monotonicity this ~= "exactly flat"

def is_plateau(top10_history: list[float], plateau_window: int) -> bool:
    if plateau_window <= 0 or len(top10_history) <= plateau_window:
        return False
    return top10_history[-1] - top10_history[-1 - plateau_window] <= PLATEAU_MIN_IMPROVEMENT
```

- Needs `plateau_window + 1` points: the latest vs. the value `plateau_window`
  generations back (a full window of non-improvement).
- `ε = PLATEAU_MIN_IMPROVEMENT = 1e-9` is a module constant. A *configurable
  improvement threshold* is the PRD open-question deferred for later tuning; the
  operator knob this slice ships is `plateau_window` (already plumbed end-to-end).

## 2. `stop_reason` integration (pure backend)

`stop_reason` gains two keyword params: `top10_history: list[float]` and
`plateau_window: int`. Termination priority becomes:

```
exhausted (FR-002 budget, hard)  >  plateaued  >  max_generations  >  no_progress
```

- Plateau outranks the generation cap because it is the informative convergence
  signal (Story 2); the hard budget guarantee (FR-002) still wins over everything.
- `plateaued` and `no_progress` are complementary: `no_progress` fires on a single
  generation that scored nothing (`made_progress=False`); `plateaued` requires a
  full window of *scored-but-flat* generations (`made_progress=True` throughout).
- `stop_check` (`loop/graph.py`) passes `[v for _, v in state["auc_curve"]]` and
  `state["plateau_window"]`.

## 3. Status propagation (no contract change)

`stop_reason → "plateaued"` rides the existing generic terminal path end-to-end:

- `stop_check` sets `state["stop_reason"] = "plateaued"`, `done=True`.
- `runner._drive` / `cli` already read `final_state["stop_reason"]` into the terminal
  `status` (no branch needed).
- `finalize_run` writes `Run.status = "plateaued"` — 9 chars, fits the existing
  `String(16)` column. **No migration.**
- The existing `run.complete` event carries `status="plateaued"`. **No WS schema
  change.**

## 4. Live plateau signal (frontend)

- Add `"plateaued"` to `LiveRun.tsx`'s `TERMINAL` set so the run is treated as
  finished (badge → secondary, Stop button hidden, WS closes on terminal).
- Add `plateau_window: number` to `RunSnapshot` (REST snapshot model +
  `_snapshot_from_state` reads `cfg.plateau_window` + `api.ts` type) so the signal
  copy can name the window concretely.
- New pure helper `plateauNotice(status, plateau_window): string | null` (mirrors
  the `runEvents.ts` / `logic.py` pure-helper pattern, unit-testable without a DOM).
  Returns the signal string only when `status === "plateaued"`, else `null`.
- `LiveRun` renders a **distinct amber callout** when `plateauNotice(...)` is
  non-null: *"Score plateaued — no improvement over N generations. Run stopped
  automatically."* This is the Story-2 signal, visually distinct from a generic
  `exhausted`/`stopped` badge.
- Liveness: plateau auto-stops → `run.complete{status:"plateaued"}` → `applyEvent`
  sets status → callout renders, within G5's <2 s.

## 5. Testing

- **pytest (pure):** `is_plateau` — flat window → True; improving → False;
  insufficient history (≤ window) → False; boundary at exactly `window+1` points;
  ε edge (improvement just below/above ε). `stop_reason` — `plateaued` when flat;
  `exhausted` outranks plateau; plateau outranks `max_generations`; continue when
  improving; `no_progress` still fires when `made_progress=False`.
- **pytest (node):** `stop_check` with a crafted flat-curve state →
  `stop_reason="plateaued"`, `done=True`.
- **vitest (frontend):** `runEvents` — `run.complete{status:"plateaued"}` sets
  status. `plateauNotice` — returns copy for `"plateaued"`, `null` for others.
- **Gates:** `uv run pytest` · `uv run mypy -p capychem -p capychem.api` ·
  `uv run ruff check .` · `pnpm --filter web test` · `pnpm --filter web typecheck`
  · `pnpm --filter web lint`.

## Out of scope / deferred

- Configurable plateau *improvement threshold* (PRD open-question) — deferred; this
  slice ships only the `plateau_window` knob with a fixed ε.
- A pre-stop "approaching plateau" warning while the run continues — rejected:
  FR-003 mandates auto-stop, so the terminal `plateaued` signal is the live signal.
- Any change to `packages/core/eval/` plateau behavior — eval runs to budget by
  design (head-to-head verdict); untouched.
