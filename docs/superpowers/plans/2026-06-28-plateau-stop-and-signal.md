# plateau-stop-and-signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the top-10 mean score stops improving for `plateau_window` consecutive generations, the product/CLI loop stops with a `plateaued` status and the watch-live view surfaces a distinct plateau signal (FR-003, Story 2, milestone-02 exit criterion 6).

**Architecture:** Add plateau detection to the shared pure `stop_reason` helper (`loop/logic.py`), wire it from the `stop_check` node (`loop/graph.py`). `"plateaued"` rides the existing generic terminal path (status → `run.complete`) with no new WS event and no DB migration. The frontend treats `"plateaued"` as terminal and renders a callout driven by a pure `plateauNotice` helper; `plateau_window` is added to the run snapshot so the copy is concrete.

**Tech Stack:** Python 3.12 (LangGraph, SQLAlchemy async, Pydantic, pytest, mypy strict, ruff) · Next.js 16 / React 19 / TypeScript (vitest, eslint).

## Global Constraints

- Pure decision helpers in `loop/logic.py` stay free of I/O / DB / harness (unit-testable, deterministic — G6).
- mypy strict + ruff on all touched Python under `apps/`, `packages/`. (`uv run mypy -p capychem -p capychem.api`, `uv run ruff check .`)
- TypeScript strict + eslint on touched web code. (`pnpm --filter web typecheck`, `pnpm --filter web lint`)
- NEVER claim real-world drug-discovery efficacy in copy (PRD N6). UI copy uses positive imperatives.
- Do NOT touch `packages/core/capychem/eval/` — it has its own loop; slice 06's beat verdict must not move.
- The survivor pool is elitist (`merge_and_truncate` keeps the global top `pop_size`), so `top10_mean` is monotonically non-decreasing — "no improvement" means flat (Δ ≤ ε).
- `ε = PLATEAU_MIN_IMPROVEMENT = 1e-9` is a module constant; a configurable improvement threshold is deferred (PRD open-question).

---

### Task 1: Plateau pure logic (`is_plateau` + `stop_reason` integration)

**Files:**
- Modify: `packages/core/capychem/loop/logic.py`
- Test: `packages/core/tests/test_loop_logic.py`

**Interfaces:**
- Consumes: `Scored` (existing).
- Produces:
  - `PLATEAU_MIN_IMPROVEMENT: float` (= `1e-9`)
  - `is_plateau(top10_history: list[float], plateau_window: int) -> bool`
  - `stop_reason(*, calls_used: int, budget: int, gen_index: int, max_generations: int, made_progress: bool, top10_history: list[float] | None = None, plateau_window: int = 0) -> str | None` — returns `"plateaued"` between `"exhausted"` and `"max_generations"`.

- [ ] **Step 1: Write the failing tests** — append to `packages/core/tests/test_loop_logic.py`:

```python
from capychem.loop.logic import is_plateau  # add to the existing import block


def test_is_plateau_flat_window_true() -> None:
    # window=3 needs 4 points; last == value 3 generations back → plateau
    assert is_plateau([0.1, 0.5, 0.5, 0.5, 0.5], plateau_window=3) is True


def test_is_plateau_improving_false() -> None:
    assert is_plateau([0.1, 0.2, 0.3, 0.4, 0.5], plateau_window=3) is False


def test_is_plateau_insufficient_history_false() -> None:
    # only window points (need window+1) → cannot judge yet
    assert is_plateau([0.5, 0.5, 0.5], plateau_window=3) is False


def test_is_plateau_boundary_exactly_window_plus_one() -> None:
    assert is_plateau([0.5, 0.5, 0.5, 0.5], plateau_window=3) is True


def test_is_plateau_improvement_just_above_epsilon_false() -> None:
    assert is_plateau([0.5, 0.5, 0.5, 0.5 + 1e-6], plateau_window=3) is False


def test_is_plateau_zero_window_false() -> None:
    assert is_plateau([0.5, 0.5, 0.5], plateau_window=0) is False


def test_stop_reason_plateaued() -> None:
    assert (
        stop_reason(
            calls_used=10, budget=100, gen_index=3, max_generations=100,
            made_progress=True, top10_history=[0.5, 0.5, 0.5, 0.5], plateau_window=3,
        )
        == "plateaued"
    )


def test_stop_reason_budget_outranks_plateau() -> None:
    assert (
        stop_reason(
            calls_used=100, budget=100, gen_index=3, max_generations=100,
            made_progress=True, top10_history=[0.5, 0.5, 0.5, 0.5], plateau_window=3,
        )
        == "exhausted"
    )


def test_stop_reason_plateau_outranks_max_generations() -> None:
    assert (
        stop_reason(
            calls_used=10, budget=100, gen_index=100, max_generations=100,
            made_progress=True, top10_history=[0.5, 0.5, 0.5, 0.5], plateau_window=3,
        )
        == "plateaued"
    )


def test_stop_reason_no_plateau_when_improving() -> None:
    assert (
        stop_reason(
            calls_used=10, budget=100, gen_index=3, max_generations=100,
            made_progress=True, top10_history=[0.1, 0.2, 0.3, 0.4], plateau_window=3,
        )
        is None
    )
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `uv run pytest packages/core/tests/test_loop_logic.py -k "plateau" -x`
Expected: FAIL — `ImportError: cannot import name 'is_plateau'` (and `stop_reason` TypeError on `top10_history`).

- [ ] **Step 3: Implement** — in `packages/core/capychem/loop/logic.py`, add the constant near `VALID_SMILES_THRESHOLD`:

```python
PLATEAU_MIN_IMPROVEMENT = 1e-9
```

Add the helper (place it just above `stop_reason`):

```python
def is_plateau(top10_history: list[float], plateau_window: int) -> bool:
    """True when the top-10 mean has not improved over the last ``plateau_window``
    generations (FR-003). The survivor pool is elitist so the history is
    monotonically non-decreasing — "no improvement" means flat (Δ ≤ ε). Needs
    ``plateau_window + 1`` points: the latest vs. the value a full window back."""
    if plateau_window <= 0 or len(top10_history) <= plateau_window:
        return False
    return top10_history[-1] - top10_history[-1 - plateau_window] <= PLATEAU_MIN_IMPROVEMENT
```

Replace the `stop_reason` signature and body:

```python
def stop_reason(
    *,
    calls_used: int,
    budget: int,
    gen_index: int,
    max_generations: int,
    made_progress: bool,
    top10_history: list[float] | None = None,
    plateau_window: int = 0,
) -> str | None:
    """Return a termination reason, or None to continue.

    Priority: budget exhaustion (FR-002, hard) > plateau (FR-003) > max-generations
    cap > zero forward progress (guards an all-invalid / all-duplicate batch from
    looping forever). Plateau outranks the gen cap because it is the informative
    convergence signal (Story 2); the hard budget guarantee still wins.
    """
    if calls_used >= budget:
        return "exhausted"
    if is_plateau(top10_history or [], plateau_window):
        return "plateaued"
    if gen_index >= max_generations:
        return "max_generations"
    if not made_progress:
        return "no_progress"
    return None
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `uv run pytest packages/core/tests/test_loop_logic.py -x`
Expected: PASS (new plateau tests + the 4 pre-existing `stop_reason` tests — they pass `top10_history`/`plateau_window` via defaults, so they are unchanged and still green).

- [ ] **Step 5: Typecheck + lint + commit**

```bash
uv run mypy -p capychem && uv run ruff check packages/core
git add packages/core/capychem/loop/logic.py packages/core/tests/test_loop_logic.py
git commit -m "feat(loop): plateau detection in stop_reason (FR-003)"
```

---

### Task 2: Wire `stop_check` to pass the curve + plateau_window

**Files:**
- Modify: `packages/core/capychem/loop/graph.py:224-252` (`stop_check`)
- Test: `packages/core/tests/test_loop_plateau.py` (new)

**Interfaces:**
- Consumes: `stop_reason(..., top10_history=, plateau_window=)` from Task 1; `LoopState` keys `auc_curve`, `plateau_window` (already declared in `state.py`).
- Produces: nothing new (behavioral wiring).

- [ ] **Step 1: Write the failing test** — create `packages/core/tests/test_loop_plateau.py`:

```python
"""Node-level test: stop_check stops a run whose top-10 mean has gone flat."""

from __future__ import annotations

import pytest

from capychem.loop.graph import stop_check
from capychem.loop.state import LoopState, Scored


def _state(curve: list[tuple[int, float]], *, plateau_window: int) -> LoopState:
    return {
        "run_id": 1,
        "calls_used": 50,
        "budget": 10_000,
        "gen_index": len(curve) - 1,
        "max_generations": 100,
        "plateau_window": plateau_window,
        "auc_curve": curve,
        "population": [Scored(smiles="CCO", score=0.5, candidate_id=1)],
        "_made_progress": True,
        "run_trace_id": None,
        "gen_span_id": None,
    }


@pytest.mark.asyncio
async def test_stop_check_stops_on_plateau() -> None:
    flat = [(10, 0.4), (20, 0.5), (30, 0.5), (40, 0.5), (50, 0.5)]
    out = await stop_check(_state(flat, plateau_window=3))
    assert out["done"] is True
    assert out["stop_reason"] == "plateaued"
    assert out["summary"] is not None


@pytest.mark.asyncio
async def test_stop_check_continues_while_improving() -> None:
    improving = [(10, 0.1), (20, 0.2), (30, 0.3), (40, 0.4), (50, 0.5)]
    out = await stop_check(_state(improving, plateau_window=3))
    assert out["done"] is False
    assert out["gen_index"] == 5  # gen_index + 1
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest packages/core/tests/test_loop_plateau.py -x`
Expected: FAIL — `test_stop_check_stops_on_plateau` returns `done=False` (plateau not yet wired into the node).

- [ ] **Step 3: Implement** — in `packages/core/capychem/loop/graph.py`, update the `stop_reason(...)` call inside `stop_check` to pass the curve + window:

```python
        reason = stop_reason(
            calls_used=state["calls_used"],
            budget=state["budget"],
            gen_index=state["gen_index"] + 1,
            max_generations=state["max_generations"],
            made_progress=state["_made_progress"],
            top10_history=[v for _, v in state.get("auc_curve", [])],
            plateau_window=state["plateau_window"],
        )
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest packages/core/tests/test_loop_plateau.py -x`
Expected: PASS (both tests).

- [ ] **Step 5: Typecheck + lint + commit**

```bash
uv run mypy -p capychem && uv run ruff check packages/core
git add packages/core/capychem/loop/graph.py packages/core/tests/test_loop_plateau.py
git commit -m "feat(loop): feed top-10 history + plateau_window into stop_check"
```

---

### Task 3: Expose `plateau_window` on the run snapshot (status propagation is generic)

**Files:**
- Modify: `apps/api/capychem/api/schemas.py:32-42` (`RunSnapshot`)
- Modify: `apps/api/capychem/api/runner.py:29-48` (`_snapshot_from_state`)
- Modify: `apps/api/capychem/api/routes_runs.py:64-74` (DB-path snapshot)
- Test: `apps/api/tests/test_runner.py:58-59` (extend existing assertion)

> NOTE: the `"plateaued"` terminal status needs NO new code — `stop_check` sets
> `state["stop_reason"]="plateaued"`, which `_drive`/`cli` already read into the
> terminal status and `finalize_run` writes to `Run.status` (fits `String(16)`),
> and the existing `run.complete` event carries it. Do not add a status branch.

**Interfaces:**
- Consumes: `RunConfig.plateau_window` (existing), `Run.plateau_window` column (existing).
- Produces: `RunSnapshot.plateau_window: int` — read by the web client (Task 4).

- [ ] **Step 1: Write the failing test** — extend the snapshot assertion in `apps/api/tests/test_runner.py::test_runner_runs_to_completion_and_emits_events` (the `cfg` already sets `plateau_window=5`):

```python
    snap = reg.snapshot(run_id)
    assert snap is not None and snap["oracle_calls_used"] <= 40
    assert snap["plateau_window"] == 5  # NEW: snapshot exposes the window for the live signal
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest apps/api/tests/test_runner.py::test_runner_runs_to_completion_and_emits_events -x`
Expected: FAIL — `KeyError: 'plateau_window'`.

- [ ] **Step 3: Implement** — three edits.

`apps/api/capychem/api/schemas.py`, add to `RunSnapshot` (after `budget`):

```python
    budget: int
    plateau_window: int
```

`apps/api/capychem/api/runner.py`, in `_snapshot_from_state`'s returned dict (after `"budget": cfg.budget,`):

```python
        "budget": cfg.budget,
        "plateau_window": cfg.plateau_window,
```

`apps/api/capychem/api/routes_runs.py`, in the DB-path `RunSnapshot(...)` (after `budget=row.budget,`):

```python
            budget=row.budget,
            plateau_window=row.plateau_window,
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest apps/api/tests/test_runner.py::test_runner_runs_to_completion_and_emits_events -x`
Expected: PASS.

- [ ] **Step 5: Typecheck + lint + commit**

```bash
uv run mypy -p capychem -p capychem.api && uv run ruff check apps/api
git add apps/api/capychem/api/schemas.py apps/api/capychem/api/runner.py apps/api/capychem/api/routes_runs.py apps/api/tests/test_runner.py
git commit -m "feat(api): expose plateau_window on the run snapshot"
```

---

### Task 4: Frontend plateau signal (`plateauNotice` + LiveRun callout)

**Files:**
- Create: `apps/web/lib/plateau.ts`
- Create: `apps/web/lib/plateau.test.ts`
- Modify: `apps/web/lib/api.ts:5-16` (`RunSnapshot` type)
- Modify: `apps/web/lib/runEvents.test.ts:5-9` (add `plateau_window` to the `base` fixture) + a new plateaued-status case
- Modify: `apps/web/app/runs/[id]/LiveRun.tsx` (`TERMINAL` set + callout render)

**Interfaces:**
- Consumes: `RunSnapshot` (gains `plateau_window: number`).
- Produces: `plateauNotice(status: string, plateauWindow: number): string | null`.

- [ ] **Step 1: Write the failing tests** — create `apps/web/lib/plateau.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { plateauNotice } from "./plateau";

describe("plateauNotice", () => {
  it("returns a signal naming the window when status is plateaued", () => {
    const msg = plateauNotice("plateaued", 5);
    expect(msg).toContain("5");
    expect(msg).toMatch(/plateau/i);
  });
  it("returns null for non-plateaued statuses", () => {
    expect(plateauNotice("running", 5)).toBeNull();
    expect(plateauNotice("exhausted", 5)).toBeNull();
    expect(plateauNotice("stopped", 5)).toBeNull();
  });
});
```

Add a plateaued-status case to `apps/web/lib/runEvents.test.ts` (inside the existing `describe`):

```typescript
  it("run.complete carries a plateaued terminal status", () => {
    const next = applyEvent(base, { type: "run.complete", run_id: 1, status: "plateaued", summary: null });
    expect(next.status).toBe("plateaued");
  });
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `pnpm --filter web test -- --run plateau runEvents`
Expected: FAIL — `plateau.ts` cannot be resolved; and `base` fixture is missing `plateau_window` once the type requires it (next step).

- [ ] **Step 3: Implement** — create `apps/web/lib/plateau.ts`:

```typescript
// Pure signal helper for the watch-live plateau callout (FR-003, Story 2).
// Returns the operator-facing message when a run stopped on plateau, else null.
export function plateauNotice(
  status: string,
  plateauWindow: number,
): string | null {
  if (status !== "plateaued") return null;
  return `Score plateaued — no improvement over ${plateauWindow} generations. Run stopped automatically.`;
}
```

Add `plateau_window` to the `RunSnapshot` type in `apps/web/lib/api.ts` (after `budget`):

```typescript
  budget: number;
  plateau_window: number;
```

Add `plateau_window: 5` to the `base` fixture in `apps/web/lib/runEvents.test.ts`:

```typescript
const base: RunSnapshot = {
  run_id: 1, task: "qed", status: "running", budget: 100, plateau_window: 5,
  generation_index: 0, oracle_calls_used: 0, best_score: null,
  top_k: [], auc_curve: [],
};
```

In `apps/web/app/runs/[id]/LiveRun.tsx`: add `"plateaued"` to the `TERMINAL` set, import the helper, and render the callout. The `TERMINAL` set becomes:

```typescript
const TERMINAL = new Set([
  "exhausted",
  "max_generations",
  "no_progress",
  "stopped",
  "errored",
  "cost_capped",
  "plateaued",
]);
```

Add the import alongside the existing `runEvents` import:

```typescript
import { plateauNotice } from "@/lib/plateau";
```

Render the callout — insert immediately after the opening `<main ...>` header `</div>` block (before the `grid grid-cols-4` stats), so the signal sits at the top of the live view:

```tsx
      {plateauNotice(snap.status, snap.plateau_window) && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {plateauNotice(snap.status, snap.plateau_window)}
        </div>
      )}
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `pnpm --filter web test -- --run`
Expected: PASS (plateau, runEvents, page suites all green).

- [ ] **Step 5: Typecheck + lint + commit**

```bash
pnpm --filter web typecheck && pnpm --filter web lint
git add apps/web/lib/plateau.ts apps/web/lib/plateau.test.ts apps/web/lib/api.ts apps/web/lib/runEvents.test.ts "apps/web/app/runs/[id]/LiveRun.tsx"
git commit -m "feat(web): surface plateau signal in watch-live (Story 2)"
```

---

### Task 5: Full gate + live plateau verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend gate**

Run: `uv run pytest && uv run mypy -p capychem -p capychem.api && uv run ruff check .`
Expected: all green (pytest count ≥ prior 130 + the new plateau tests).

- [ ] **Step 2: Run the full web gate**

Run: `pnpm --filter web test -- --run && pnpm --filter web typecheck && pnpm --filter web lint`
Expected: all green.

- [ ] **Step 3: Manual live plateau check (best-effort, document result)**

Launch a graph_ga jnk3/qed run with a small `plateau_window` (e.g. 2) and a large budget so it converges before exhausting; confirm in watch-live that the run ends with the `plateaued` badge and the amber callout naming the window. If the local stack (api + web + harness) is not running this session, note that this step was deferred to a manual pass and rely on the unit/node coverage. Do NOT claim it passed without observing it.

- [ ] **Step 4: No commit** — verification only; the slice-ship ritual (milestone/handoff/slice-doc + merge) is handled separately.

---

## Self-Review

**Spec coverage:**
- FR-003 plateau stop → Tasks 1 (logic) + 2 (node wiring). ✓
- `"plateaued"` status → generic propagation (Task 3 note), verified via Task 2 node test + existing status-propagation tests. ✓
- Live plateau signal (Story 2, exit criterion 6) → Task 4 (`plateauNotice` + callout) + Task 3 (`plateau_window` on snapshot). ✓
- Scope boundary (no eval/ change, no WS event, no migration) → Global Constraints + Task 3 note. ✓
- ε / monotonicity rationale → Global Constraints + Task 1 docstring. ✓

**Placeholder scan:** none — every code step shows the code; every run step shows the command + expected outcome. ✓

**Type consistency:** `plateauNotice(status, plateauWindow)` consistent across Task 4 helper + test + LiveRun call. `stop_reason(..., top10_history, plateau_window)` consistent across Task 1 def + Task 2 call site. `RunSnapshot.plateau_window: int` (py) / `plateau_window: number` (ts) consistent across schema, runner, route, api.ts, fixture. ✓
