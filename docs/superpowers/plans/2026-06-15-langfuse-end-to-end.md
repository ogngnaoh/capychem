# Langfuse End-to-End — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-load `.env.local`, add the missing per-generation span so the Langfuse trace is a true **run→generation→node** hierarchy, and verify a real nested trace is viewable (FR-014).

**Architecture:** A small idempotent dotenv loader wired at the loop entrypoints; `trace.py` gains real observation-nesting (`parent_observation_id`) + a generation-level span whose live handle lives in an in-process registry (so it survives across the five separate LangGraph node calls); `state.py`/`graph.py` thread a run-trace id distinct from the current generation-span id. Lightweight structural metadata only.

**Tech Stack:** Langfuse Python SDK v2 (`langfuse==2.60.10`, self-hosted on `:3001`), python-dotenv, pytest.

**Constraints:** Tracing must NEVER break the loop (every helper stays exception-safe — existing invariant). Keys stay in `.env.local` (gitignored) / env only; never commit (SPEC §8.1). Verification screenshots must not expose secret values.

**Worktree/env note:** This slice runs worktree-isolated, concurrent with slice 1. Its unit tests are mock-based (harness-free). The real-loop verification (Task 5) is best run from the MAIN checkout (it needs the harness venv + the loaded `.env.local`).

**Reference (confirm before use — quoted from an Explore pass):**
- `trace.py` today: `is_enabled()`, `trace_run(run_id, task) -> str|None` (returns the trace id), `@contextmanager span(name, *, parent_id, **metadata)` (passes `trace_id=parent_id` — only nests under the *trace*), `flush()`. Lazy module-global `_client = Langfuse()`.
- `graph.py`: all 5 nodes already do `with trace.span("node:X", parent_id=state.get("gen_span_id")): ...` at lines ~50/68/72/90/143.
- `cli.py:60,76-77`: `run_span_id = trace.trace_run(...)`; initial state sets `run_span_id` and `gen_span_id` both to `run_span_id`; `flush()` at cli.py:90.
- `apps/api/capychem/api/runner.py:136,151-152,246`: same pattern in `_drive`; `flush()` at 246.
- `state.py:39-41`: `LoopState` defines `gen_span_id` (+ likely `run_span_id`).
- **v2 nesting:** `client.span(name=..., trace_id=<trace id>, parent_observation_id=<parent span id>, metadata=...)`. Confirm `parent_observation_id` is accepted by `langfuse 2.60.10`; if not, switch to stateful chaining (`trace_obj.span(...).span(...)`) — the registry already holds live handles, so chaining is a clean fallback.

---

### Task 1: `env.py` — idempotent dotenv loader + dependency

**Files:**
- Modify: `packages/core/pyproject.toml` — add `python-dotenv` to `[project.dependencies]`
- Create: `packages/core/capychem/env.py`
- Test: `packages/core/tests/test_env.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_env.py
from pathlib import Path
import capychem.env as env


def test_load_local_env_sets_vars(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    envfile = tmp_path / ".env.local"
    envfile.write_text("CAPYCHEM_TEST_KEY=hello\n")
    monkeypatch.delenv("CAPYCHEM_TEST_KEY", raising=False)
    env.load_local_env(path=envfile)
    import os
    assert os.environ["CAPYCHEM_TEST_KEY"] == "hello"


def test_load_local_env_missing_file_is_noop(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # must not raise when the file is absent
    env.load_local_env(path=tmp_path / "nope.env")


def test_load_local_env_is_idempotent(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    envfile = tmp_path / ".env.local"
    envfile.write_text("CAPYCHEM_TEST_KEY=one\n")
    monkeypatch.delenv("CAPYCHEM_TEST_KEY", raising=False)
    env.load_local_env(path=envfile)
    env.load_local_env(path=envfile)  # second call must not raise
    import os
    assert os.environ["CAPYCHEM_TEST_KEY"] == "one"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/core/tests/test_env.py -x`
Expected: FAIL — `ModuleNotFoundError: capychem.env`

- [ ] **Step 3: Add the dependency + implement**

Modify `packages/core/pyproject.toml` `[project.dependencies]` (append):
```toml
  "python-dotenv>=1.0",
```

```python
# packages/core/capychem/env.py
"""Load local secrets from .env.local into the process env (idempotent).

Called at each loop entrypoint so Langfuse keys (and any other local secrets)
are present without the operator having to export them. .env.local is gitignored
(SPEC §8.1) — never commit it.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _default_path() -> Path:
    # packages/core/capychem/env.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3] / ".env.local"


def load_local_env(path: Path | None = None) -> None:
    """Load `.env.local` if present. Does not override already-set env vars."""
    target = path or _default_path()
    if target.exists():
        load_dotenv(dotenv_path=os.fspath(target), override=False)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv sync && uv run pytest packages/core/tests/test_env.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add packages/core/pyproject.toml packages/core/capychem/env.py packages/core/tests/test_env.py
git commit -m "feat(env): idempotent .env.local loader"
```

---

### Task 2: Wire `load_local_env` at the loop entrypoints

**Files:**
- Modify: `packages/core/capychem/cli.py` — call at the top of `main()`
- Modify: `apps/api/capychem/api/main.py` — call in the FastAPI lifespan startup

(The `capychem-eval` CLI is intentionally NOT wired — the eval runner needs no Langfuse/env, and wiring it would create a cross-slice dependency on slice 1's not-yet-merged `eval/cli.py`.)

- [ ] **Step 1: Wire the CLI**

In `packages/core/capychem/cli.py`, at the very top of `main(argv)` (before parsing/running):
```python
    from capychem.env import load_local_env
    load_local_env()
```

- [ ] **Step 2: Wire the FastAPI lifespan**

In `apps/api/capychem/api/main.py`, in the lifespan startup (before the DB engine init at ~line 23):
```python
    from capychem.env import load_local_env
    load_local_env()
```

- [ ] **Step 3: Verify nothing broke**

Run: `uv run pytest packages/core/tests/test_cli_e2e.py -x` (harness-backed; confirms the CLI still runs end-to-end with the loader call in place)
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add packages/core/capychem/cli.py apps/api/capychem/api/main.py
git commit -m "feat(env): load .env.local at capychem-run + FastAPI startup"
```

---

### Task 3: `trace.py` — observation nesting + generation span (load-bearing)

**Files:**
- Modify: `packages/core/capychem/loop/trace.py`
- Test: `packages/core/tests/test_trace.py` (extend the existing `_fake_client` pattern)

- [ ] **Step 1: Write the failing tests** (extend `test_trace.py`; reuse its `monkeypatch`-set keys + fake client, augmenting the fake to record `parent_observation_id` and span `.end()`s)

```python
# add to packages/core/tests/test_trace.py
def test_span_threads_parent_observation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    calls: list[dict] = []

    class _Span:
        id = "span-1"
        def end(self) -> None: ...

    class _Client:
        def span(self, **kw):  # type: ignore[no-untyped-def]
            calls.append(kw)
            return _Span()

    monkeypatch.setattr(trace, "_get_client", lambda: _Client())
    with trace.span("node:propose", trace_id="trace-1", parent_observation_id="gen-1"):
        pass
    assert calls[0]["trace_id"] == "trace-1"
    assert calls[0]["parent_observation_id"] == "gen-1"


def test_gen_span_opens_under_trace_and_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    ended: list[bool] = []

    class _Span:
        id = "gen-span-9"
        def end(self) -> None: ended.append(True)

    class _Client:
        def span(self, **kw):  # type: ignore[no-untyped-def]
            assert kw["trace_id"] == "trace-1"
            assert kw.get("parent_observation_id") is None  # gen span is a direct child of the trace
            return _Span()

    monkeypatch.setattr(trace, "_get_client", lambda: _Client())
    sid = trace.gen_span("trace-1", run_id=7, gen_index=0)
    assert sid == "gen-span-9"
    trace.end_gen_span(run_id=7, gen_index=0)
    assert ended == [True]
    trace.end_gen_span(run_id=7, gen_index=0)  # idempotent: second end is a safe no-op
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/core/tests/test_trace.py -x`
Expected: FAIL — `span()` rejects `trace_id`/`parent_observation_id` kwargs; `gen_span` undefined.

- [ ] **Step 3: Modify `trace.py`**

Change `span()` to take `trace_id` + `parent_observation_id` (replacing the old `parent_id`), and add the gen-span registry + helpers:

```python
# replace the existing span() signature/body:
@contextmanager
def span(
    name: str,
    *,
    trace_id: str | None,
    parent_observation_id: str | None = None,
    **metadata: Any,
) -> Iterator[str | None]:
    """Context manager yielding the new span's id. Nests under `trace_id`
    (the run trace) and, when given, under `parent_observation_id` (the
    enclosing generation span)."""
    if not is_enabled():
        yield None
        return
    sp = None
    try:
        sp = _get_client().span(
            name=name, trace_id=trace_id,
            parent_observation_id=parent_observation_id, metadata=metadata or None,
        )
    except Exception:  # noqa: BLE001 - tracing must never break the loop
        sp = None
    try:
        yield str(sp.id) if sp is not None else None
    finally:
        if sp is not None:
            try:
                sp.end()
            except Exception:  # noqa: BLE001
                pass


# add near the bottom of the module:
_gen_spans: dict[tuple[int, int], Any] = {}


def gen_span(run_trace_id: str | None, run_id: int, gen_index: int, **metadata: Any) -> str | None:
    """Open a generation-level span as a direct child of the run trace; register
    its live handle so it can be ended at the generation boundary. None when
    disabled or trace absent."""
    if not is_enabled() or run_trace_id is None:
        return None
    try:
        sp = _get_client().span(
            name=f"generation:{gen_index}", trace_id=run_trace_id, metadata=metadata or None,
        )
    except Exception:  # noqa: BLE001
        return None
    _gen_spans[(run_id, gen_index)] = sp
    return str(sp.id)


def end_gen_span(run_id: int, gen_index: int) -> None:
    """End + de-register a generation span. Safe no-op if missing/disabled."""
    sp = _gen_spans.pop((run_id, gen_index), None)
    if sp is not None:
        try:
            sp.end()
        except Exception:  # noqa: BLE001
            pass
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/core/tests/test_trace.py -v`
Expected: all pass (existing no-op tests + 2 new). Note: existing tests that call `span(..., parent_id=...)` must be updated to the new `trace_id=`/`parent_observation_id=` kwargs.

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/loop/trace.py packages/core/tests/test_trace.py
git commit -m "feat(trace): observation nesting + generation span registry"
```

---

### Task 4: Thread the gen span through the loop (run→generation→node)

**Files:**
- Modify: `packages/core/capychem/loop/state.py` — add `run_trace_id`; keep `gen_span_id` (now the *current generation* span, updated per gen)
- Modify: `packages/core/capychem/loop/graph.py` — open gen span in `propose`, end it in `stop_check`, update node spans to the new kwargs
- Modify: `packages/core/capychem/cli.py` + `apps/api/capychem/api/runner.py` — set `run_trace_id` from `trace_run(...)`, init `gen_span_id=None`
- Test: `packages/core/tests/test_trace_nesting.py` (new — harness/DB-free node-level test)

- [ ] **Step 1: Write the failing test** (gen-0 `propose` is a pure file read — no harness, no DB — so we can drive it directly with a recording trace)

```python
# packages/core/tests/test_trace_nesting.py
import pytest
from capychem.loop import graph as graph_mod


@pytest.mark.asyncio
async def test_propose_opens_gen_span_and_stop_check_ends_it(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[tuple[int, int]] = []
    ended: list[tuple[int, int]] = []
    monkeypatch.setattr(graph_mod.trace, "gen_span",
                        lambda tid, run_id, gen_index, **md: (opened.append((run_id, gen_index)) or "gen-x"))
    monkeypatch.setattr(graph_mod.trace, "end_gen_span",
                        lambda run_id, gen_index: ended.append((run_id, gen_index)))
    # node spans -> harmless no-op context manager
    import contextlib
    monkeypatch.setattr(graph_mod.trace, "span",
                        lambda *a, **k: contextlib.nullcontext("node-x"))

    state = {"run_id": 7, "run_trace_id": "trace-1", "gen_span_id": None, "gen_index": 0,
             "task": "qed", "seed": 42, "pop_size": 5, "budget": 100, "calls_used": 0}
    out = await graph_mod.propose(state)              # gen 0: loads starting pop, opens gen span
    assert opened == [(7, 0)]
    assert out["gen_span_id"] == "gen-x"

    state.update(out)
    state["_made_progress"] = True
    await graph_mod.stop_check(state)                 # ends the gen span for this generation
    assert ended == [(7, 0)]
```

(If `propose`/`stop_check` need more state keys, copy them from `LoopState` in `state.py`; keep the test harness/DB-free by only exercising gen-0 propose, which reads the `.smi` file.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/core/tests/test_trace_nesting.py -x`
Expected: FAIL — `propose` doesn't open a gen span yet / `run_trace_id` not threaded.

- [ ] **Step 3: Implement the wiring**

`state.py` — add to `LoopState`:
```python
    run_trace_id: str | None   # the run-level Langfuse trace id (set once)
    # gen_span_id stays; it now holds the CURRENT generation span id (updated each gen)
```

`graph.py`:
- In `propose`, before the node body, open the gen span and thread it:
```python
async def propose(state: LoopState) -> dict[str, Any]:
    gen_span_id = trace.gen_span(
        state.get("run_trace_id"), state["run_id"], state["gen_index"],
        gen_index=state["gen_index"], calls_used=state["calls_used"],
    )
    with trace.span("node:propose", trace_id=state.get("run_trace_id"), parent_observation_id=gen_span_id):
        ...  # existing body
    return {..., "gen_span_id": gen_span_id}   # include gen_span_id in the returned update
```
- In `validate`/`score`/`persist`/`stop_check`, change each node span to:
```python
    with trace.span("node:<name>", trace_id=state.get("run_trace_id"),
                    parent_observation_id=state.get("gen_span_id")):
```
- At the END of `stop_check` (after deciding continue/stop, before returning), end the current generation span:
```python
    trace.end_gen_span(state["run_id"], state["gen_index"])
```

`cli.py` (and `runner.py` `_drive`): replace the run-level wiring:
```python
    run_trace_id = trace.trace_run(run_id, args.task)   # cli.py; cfg.task in runner.py
    ...
    initial: LoopState = {
        ...
        "run_trace_id": run_trace_id,
        "gen_span_id": None,
        ...
    }
```
(Remove the old `run_span_id`/`gen_span_id=run_span_id` lines.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/core/tests/test_trace_nesting.py packages/core/tests/test_cli_e2e.py -v`
Expected: nesting test PASS; e2e still PASS (no-op tracing when keys absent).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/loop/state.py packages/core/capychem/loop/graph.py packages/core/capychem/cli.py apps/api/capychem/api/runner.py packages/core/tests/test_trace_nesting.py
git commit -m "feat(trace): thread run-trace + per-generation span through the loop"
```

---

### Task 5: Real-key nesting verification (orchestrator-run — FR-014 evidence)

Run by the orchestrator during VERIFY, from the MAIN checkout with `.env.local` present and Langfuse up on `:3001`. Not a CI test (no keys in CI).

- [ ] **Step 1: Run a small traced loop**

Run: `uv run capychem-run --task qed --budget 60 --pop-size 20 --offspring 10 --seed 42`
Expected: completes; `flush()` lands the trace.

- [ ] **Step 2: Programmatically assert the nesting**

Fetch the trace via the Langfuse SDK/API (`from langfuse import Langfuse; Langfuse().get_trace(<id>)` or the observations endpoint) and assert the observation tree is **run → generation:N → node:\***. Capture the assertion output as evidence.

- [ ] **Step 3: Manual UI confirmation**

Open `http://localhost:3001`, find the run trace, confirm the nested run→generation→node structure renders, and screenshot it (no secret values in frame). Record in the slice doc + handoff.

---

## Self-Review (completed by plan author)

- **Spec coverage:** dotenv dep+loader (Task 1) ✓; wired at entrypoints (Task 2) ✓; `parent_observation_id` nesting + gen span + registry (Task 3) ✓; run-trace/gen-span threading through loop + both entrypoints (Task 4) ✓; programmatic + manual FR-014 verification (Task 5) ✓. Lightweight metadata baked into Task 4's `propose` gen-span call.
- **Placeholder scan:** none. "Confirm `parent_observation_id` against 2.60.10" is a real verification instruction with a concrete fallback (stateful chaining), not a placeholder.
- **Type consistency:** `gen_span(run_trace_id, run_id, gen_index)` / `end_gen_span(run_id, gen_index)` / `span(name, *, trace_id, parent_observation_id)` signatures identical across Tasks 3/4. `run_trace_id` + `gen_span_id` state keys consistent across `state.py`/`graph.py`/`cli.py`/`runner.py`.
- **Coordination:** only `[project.dependencies]` touched in `pyproject.toml` (slice 1 touches `[project.scripts]`) — trivial merge. Eval CLI deliberately not wired (decouples from slice 1).
