# analyzer-live-surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the analyzer's per-generation hypotheses live over the run WebSocket and as a full per-generation sequence in the run view — completing milestone 03.

**Architecture:** The core loop (`packages/core`) accumulates each formed hypothesis into a `state["analyzer_hypotheses"]` list (mirroring how `auc_curve` is accumulated for observation). The in-process runner (`apps/api`) *observes* that list growing in its `astream` loop and broadcasts an `analyzer.hypothesis` WS event — exactly how it already broadcasts `generation.complete` by watching `auc_curve`. The core loop never imports or knows about the WS layer. The full historical sequence is served from the durable `AnalyzerHypothesis` DB rows via a new `hypotheses` field on `RunSnapshot` (REST). The web `LiveRun` component (which backs both watch-live and run-detail) renders one unified "Analyzer reasoning" section, newest-first, latest expanded.

**Tech Stack:** Python 3.12, LangGraph, FastAPI, Pydantic v2, SQLAlchemy async; Next.js 16 / React 19 / TypeScript 5 / Tailwind / shadcn-ui; pytest, mypy strict, ruff; vitest, tsc, eslint.

## Global Constraints

- Surface-only slice: **no analyzer logic / prompt / conditioning change; no eval; no LLM or oracle spend.**
- The core loop is **never modified to know about the WS layer** — the runner observes loop state only (`runner.py` module docstring contract). Do not thread the API `RunHandle` into `packages/core`.
- `mypy` strict on all touched `apps/` + `packages/` code: `uv run mypy -p capychem -p capychem.api`.
- Validate-every-SMILES, cost-as-first-class, Langfuse-span-per-node rules are unaffected (no new node; the `analyze` node already exists and is spanned).
- WS event name + payload per SPEC §6.3: `analyzer.hypothesis` `{after_generation_index, text, structured_json}`.
- `Hypothesis.structured` is `{"focus": str, "avoid": list[str]} | None` — `avoid` is a **list of strings**, `structured_json` may be `null` (neutral / "no new signal" fallback).
- The analyzer runs on **LLM runs, gen ≥1 only** — Graph-GA runs and gen 0 have no hypothesis; the empty case is first-class, never an error.
- TDD per task: failing test → run-it-fails → minimal impl → run-it-passes → commit. Frequent commits.

---

### Task 1: Loop-state hypothesis accumulation (`packages/core`)

Make the loop accumulate a surface-ready record per formed hypothesis, so the runner can observe it (no WS knowledge in core).

**Files:**
- Modify: `packages/core/capychem/loop/state.py` (add `HypothesisRecord` TypedDict + `analyzer_hypotheses` LoopState key)
- Modify: `packages/core/capychem/loop/graph.py:262-280` (append the record in `_analyze`)
- Test: `packages/core/tests/test_loop_analyze.py` (new test, reuses the existing `sm` fixture + `_run` helper)

**Interfaces:**
- Produces: `HypothesisRecord = TypedDict("after_generation_index": int, "text": str, "structured_json": dict[str, Any] | None)`; `LoopState["analyzer_hypotheses"]: list[HypothesisRecord]`. The runner (Task 2) and REST (Task 3) consume this exact record shape.

- [ ] **Step 1: Write the failing test**

Add to `packages/core/tests/test_loop_analyze.py` (the `sm` fixture, `_initial`, and `_run` helper already exist in this file):

```python
async def test_analyze_accumulates_surface_record_list(sm, monkeypatch) -> None:
    """Each LLM gen>=1 appends a {after_generation_index, text, structured_json}
    record to state['analyzer_hypotheses'], in order, mirroring the persisted rows."""
    cfg = RunConfig(task="qed", budget=200, seed=42, pop_size=6, offspring=4,
                    mutation_rate=0.01, plateau_window=9, max_generations=3,
                    mutation_strategy="llm")
    run_id, final = await _run(sm, cfg, monkeypatch)
    recs = final.get("analyzer_hypotheses")
    assert recs and len(recs) >= 1
    assert all(r["after_generation_index"] >= 1 for r in recs)
    assert all(isinstance(r["text"], str) and r["text"] for r in recs)
    idxs = [r["after_generation_index"] for r in recs]
    assert idxs == sorted(idxs)  # appended in generation order
    # the surface list mirrors the persisted AnalyzerHypothesis rows
    async with sm() as s:
        rows = (
            await s.execute(
                select(AnalyzerHypothesis).order_by(AnalyzerHypothesis.after_generation_index)
            )
        ).scalars().all()
    assert [r["after_generation_index"] for r in recs] == [row.after_generation_index for row in rows]
    assert [r["text"] for r in recs] == [row.text for row in rows]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_loop_analyze.py::test_analyze_accumulates_surface_record_list -x`
Expected: FAIL — `final.get("analyzer_hypotheses")` is `None` (key not yet produced).

- [ ] **Step 3: Add the record type + state key**

In `packages/core/capychem/loop/state.py`, after the `Scored` dataclass / imports (the file already imports `Any, TypedDict`), add the record type above `LoopState`:

```python
class HypothesisRecord(TypedDict):
    """Surface-ready snapshot of one persisted hypothesis. Accumulated in
    ``LoopState`` purely so the in-process runner can observe and broadcast it —
    the loop itself never touches the WS layer."""

    after_generation_index: int
    text: str
    structured_json: dict[str, Any] | None
```

Then add the key inside `LoopState` (next to `analyzer_hypothesis`):

```python
    analyzer_hypothesis: Hypothesis | None  # hypothesis threaded to next propose
    analyzer_hypotheses: list[HypothesisRecord]  # append-only surface log (runner observes)
    gen_db_id: int  # just-persisted Generation row id for analyze link
```

- [ ] **Step 4: Append the record in `_analyze`**

In `packages/core/capychem/loop/graph.py`, update the import from `.state` to include `HypothesisRecord` (the line already imports `LoopState`; add the name), then change the `_analyze` return block (currently lines 277-280):

```python
        record: HypothesisRecord = {
            "after_generation_index": state["gen_index"],
            "text": effective.text,
            "structured_json": effective.structured,
        }
        return {
            "analyzer_hypothesis": effective,
            "analyzer_hypotheses": [*state.get("analyzer_hypotheses", []), record],
            "llm_cost_usd": state.get("llm_cost_usd", 0.0) + result.cost_usd,
        }
```

(The early `return {}` for non-LLM / gen 0 is unchanged — those runs never set the key, so `state.get(...)` yields `[]` everywhere downstream.)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_loop_analyze.py -x`
Expected: PASS (the new test plus the existing analyze-node tests).

- [ ] **Step 6: Typecheck + lint + commit**

Run: `uv run mypy -p capychem -p capychem.api && uv run ruff check packages/core`
Expected: clean.

```bash
git add packages/core/capychem/loop/state.py packages/core/capychem/loop/graph.py packages/core/tests/test_loop_analyze.py
git commit -m "feat(core): accumulate analyzer_hypotheses surface log in loop state"
```

---

### Task 2: WS `analyzer.hypothesis` event + runner broadcast (`apps/api`)

Add the event schema and have the runner broadcast each new record it observes — mirroring the `generation.complete` / `auc_curve` pattern.

**Files:**
- Modify: `apps/api/capychem/api/schemas.py` (add `AnalyzerHypothesisOut` + `AnalyzerHypothesisEvent`)
- Modify: `apps/api/capychem/api/runner.py` (import the event; `last_hyp_len` tracker; observe + broadcast)
- Test: `apps/api/tests/test_runner.py` (new fast FakeGraph test)

**Interfaces:**
- Consumes: `LoopState["analyzer_hypotheses"]` records from Task 1.
- Produces: `AnalyzerHypothesisEvent(type="analyzer.hypothesis", after_generation_index, text, structured_json)` and `AnalyzerHypothesisOut(after_generation_index, text, structured_json)` — Task 3 reuses `AnalyzerHypothesisOut`.

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_runner.py` (imports `RunRegistry`, `RunConfig`, `Any` already present at top):

```python
async def test_drive_broadcasts_analyzer_hypothesis_events(monkeypatch) -> None:
    """The runner observes analyzer_hypotheses growth in loop state and broadcasts
    one analyzer.hypothesis event per new record. Fast + isolated: a fake graph
    streams the growing list directly; the core loop is never touched."""
    from capychem.api import runner as runner_mod
    from capychem.db.models import Base
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    class FakeGraph:
        async def astream(self, initial, *, config, stream_mode):  # type: ignore[no-untyped-def]
            yield {
                **initial,
                "analyzer_hypotheses": [
                    {"after_generation_index": 1, "text": "h1",
                     "structured_json": {"focus": "amide", "avoid": ["phenol"]}},
                ],
            }
            yield {
                **initial,
                "analyzer_hypotheses": [
                    {"after_generation_index": 1, "text": "h1",
                     "structured_json": {"focus": "amide", "avoid": ["phenol"]}},
                    {"after_generation_index": 2, "text": "h2", "structured_json": None},
                ],
            }

    monkeypatch.setattr(runner_mod, "build_graph", lambda sm_: FakeGraph())

    reg = RunRegistry(sm)
    run_id = await reg.start_run(
        RunConfig(task="qed", budget=10, seed=1, pop_size=4, offspring=4,
                  mutation_rate=0.01, plateau_window=2, max_generations=2,
                  mutation_strategy="llm")
    )
    queue = reg.subscribe(run_id)
    events: list[dict[str, Any]] = []
    async with asyncio.timeout(10):
        while True:
            ev = await queue.get()
            events.append(ev)
            if ev["type"] == "run.complete":
                break
    hyps = [e for e in events if e["type"] == "analyzer.hypothesis"]
    assert [h["after_generation_index"] for h in hyps] == [1, 2]
    assert hyps[0]["text"] == "h1"
    assert hyps[0]["structured_json"] == {"focus": "amide", "avoid": ["phenol"]}
    assert hyps[1]["structured_json"] is None
    await engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/tests/test_runner.py::test_drive_broadcasts_analyzer_hypothesis_events -x`
Expected: FAIL — no `analyzer.hypothesis` events broadcast (`hyps` is empty → assertion error).

- [ ] **Step 3: Add the event schemas**

In `apps/api/capychem/api/schemas.py`, add after `RunSnapshot` (before `GenerationCompleteEvent`):

```python
class AnalyzerHypothesisOut(BaseModel):
    after_generation_index: int
    text: str
    structured_json: dict[str, Any] | None = None


class AnalyzerHypothesisEvent(AnalyzerHypothesisOut):
    type: Literal["analyzer.hypothesis"] = "analyzer.hypothesis"
```

- [ ] **Step 4: Observe + broadcast in the runner**

In `apps/api/capychem/api/runner.py`:

Extend the schemas import (currently `from capychem.api.schemas import GenerationCompleteEvent, RunCompleteEvent, TopMolecule`):

```python
from capychem.api.schemas import (
    AnalyzerHypothesisEvent,
    GenerationCompleteEvent,
    RunCompleteEvent,
    TopMolecule,
)
```

Add a tracker next to `last_curve_len = 0` (currently line 160):

```python
        last_curve_len = 0
        last_hyp_len = 0
```

Inside the `async for state in stream:` loop, immediately after `final_state = state` (currently line 175) and BEFORE the `if len(state.get("auc_curve", [])) > last_curve_len:` block, add the independent hypothesis-observation (placed first so a later cost-cap/cancel `break` never drops an already-formed hypothesis):

```python
                hyps = state.get("analyzer_hypotheses", [])
                if len(hyps) > last_hyp_len:
                    for rec in hyps[last_hyp_len:]:
                        handle.broadcast(
                            AnalyzerHypothesisEvent(
                                after_generation_index=rec["after_generation_index"],
                                text=rec["text"],
                                structured_json=rec["structured_json"],
                            ).model_dump()
                        )
                    last_hyp_len = len(hyps)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest apps/api/tests/test_runner.py -x`
Expected: PASS (new test + the existing runner tests).

- [ ] **Step 6: Typecheck + lint + commit**

Run: `uv run mypy -p capychem -p capychem.api && uv run ruff check apps/api`
Expected: clean.

```bash
git add apps/api/capychem/api/schemas.py apps/api/capychem/api/runner.py apps/api/tests/test_runner.py
git commit -m "feat(api): broadcast analyzer.hypothesis WS event from the runner observer"
```

---

### Task 3: `hypotheses` on `RunSnapshot` via DB query (`apps/api`)

Serve the full historical sequence from the durable rows so a reloaded / completed run renders its hypotheses (WS only replays the terminal event).

**Files:**
- Modify: `apps/api/capychem/api/schemas.py` (add `hypotheses` to `RunSnapshot`)
- Modify: `apps/api/capychem/api/routes_runs.py` (`_hypotheses_for` helper; query in both `get_run_endpoint` branches)
- Test: `apps/api/tests/test_api.py` (fast `_hypotheses_for` unit test; GA-empty assertion; LLM end-to-end)

**Interfaces:**
- Consumes: `AnalyzerHypothesisOut` (Task 2); `AnalyzerHypothesis` model (`run_id`, `after_generation_index`, `text`, `structured_json`).
- Produces: `RunSnapshot.hypotheses: list[AnalyzerHypothesisOut]` (default `[]`); `_hypotheses_for(session, run_id) -> list[AnalyzerHypothesisOut]`.

- [ ] **Step 1: Write the failing tests**

Add to `apps/api/tests/test_api.py`. First a fast, deterministic unit test for the query helper (inserts rows directly — no loop, no harness):

```python
async def test_hypotheses_for_returns_rows_ordered() -> None:
    from capychem.api.routes_runs import _hypotheses_for
    from capychem.db.models import AnalyzerHypothesis, Run
    from capychem.db.session import init_schema, make_engine, make_sessionmaker

    engine = make_engine()
    await init_schema(engine)
    sm = make_sessionmaker(engine)
    async with sm() as s:
        run = Run(task="jnk3", budget=100, plateau_window=5, status="running",
                  mutation_strategy="llm", seed=42, config_json={})
        s.add(run)
        await s.flush()
        s.add_all([
            AnalyzerHypothesis(run_id=run.id, after_generation_index=2, text="second",
                               structured_json=None),
            AnalyzerHypothesis(run_id=run.id, after_generation_index=1, text="first",
                               structured_json={"focus": "amide", "avoid": ["phenol"]}),
        ])
        await s.commit()
        out = await _hypotheses_for(s, run.id)
    assert [h.after_generation_index for h in out] == [1, 2]
    assert out[0].text == "first"
    assert out[0].structured_json == {"focus": "amide", "avoid": ["phenol"]}
    assert out[1].structured_json is None
    await engine.dispose()
```

> NOTE for the implementer: confirm `Run(...)`'s required columns against `capychem/db/models.py` before running — pass exactly the non-nullable fields the model declares (the kwargs above mirror the columns referenced in `routes_runs.py`). Adjust if the model requires more.

Then assert the empty case on the existing graph_ga WS test. In `test_create_then_snapshot_then_complete_over_ws`, after the existing `snap = (await c.get(...)).json()` line (currently line 50) add:

```python
            assert snap["hypotheses"] == []  # graph_ga run has no analyzer hypotheses
```

Then the LLM end-to-end (stub backends are the test default; needs gen ≥1):

```python
async def test_llm_run_emits_and_lists_analyzer_hypotheses() -> None:
    body = {**_BODY, "mutation_strategy": "llm", "budget": 120, "max_generations": 8}
    async with app.router.lifespan_context(app):
        async with _client() as c:
            run_id = (await c.post("/runs", json=body)).json()["run_id"]
            types: list[str] = []
            async with asyncio.timeout(180):
                async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
                    while True:
                        msg = await ws.receive_json()
                        if msg["type"] == "ping":
                            continue
                        types.append(msg["type"])
                        if msg["type"] == "run.complete":
                            break
            assert "analyzer.hypothesis" in types
            snap = (await c.get(f"/runs/{run_id}")).json()
            assert len(snap["hypotheses"]) >= 1
            assert all(h["after_generation_index"] >= 1 for h in snap["hypotheses"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest apps/api/tests/test_api.py::test_hypotheses_for_returns_rows_ordered -x`
Expected: FAIL — `ImportError: cannot import name '_hypotheses_for'`.

- [ ] **Step 3: Add the `hypotheses` field**

In `apps/api/capychem/api/schemas.py`, add to `RunSnapshot` (after `cost_so_far_usd`):

```python
    cost_so_far_usd: float = 0.0
    hypotheses: list[AnalyzerHypothesisOut] = []
```

(`AnalyzerHypothesisOut` is defined later in the file; forward reference is fine because `from __future__ import annotations` is active at the top of `schemas.py`. If mypy/pydantic complains about ordering, move the `AnalyzerHypothesisOut` class definition above `RunSnapshot`.)

- [ ] **Step 4: Add the query helper + wire both branches**

In `apps/api/capychem/api/routes_runs.py`, extend imports:

```python
from capychem.api.schemas import AnalyzerHypothesisOut, CreateRunRequest, RunSnapshot
from capychem.db.models import AnalyzerHypothesis, Run
from sqlalchemy import select
```

Add the helper above `get_run_endpoint`:

```python
async def _hypotheses_for(
    session: AsyncSession, run_id: int
) -> list[AnalyzerHypothesisOut]:
    rows = (
        await session.execute(
            select(AnalyzerHypothesis)
            .where(AnalyzerHypothesis.run_id == run_id)
            .order_by(AnalyzerHypothesis.after_generation_index)
        )
    ).scalars().all()
    return [
        AnalyzerHypothesisOut(
            after_generation_index=r.after_generation_index,
            text=r.text,
            structured_json=r.structured_json,
        )
        for r in rows
    ]
```

Replace the body of `get_run_endpoint` so both branches attach hypotheses (one read session covers both):

```python
@router.get("/runs/{run_id}", response_model=RunSnapshot)
async def get_run_endpoint(run_id: int, request: Request) -> RunSnapshot:
    sm = sessionmaker_of(request)
    async with sm() as session:
        hyps = await _hypotheses_for(session, run_id)
        live = registry_of(request).snapshot(run_id)
        if live is not None:
            return RunSnapshot(**live, hypotheses=hyps)
        row = await session.get(Run, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        summary = row.summary_json or {}
        top = summary.get("top_k", [])
        return RunSnapshot(
            run_id=row.id,
            task=row.task,
            status=row.status,
            budget=row.budget,
            plateau_window=row.plateau_window,
            generation_index=summary.get("generations", 0),
            oracle_calls_used=summary.get("oracle_calls", 0),
            best_score=(top[0]["score"] if top else None),
            top_k=top,
            auc_curve=summary.get("auc_curve", []),
            hypotheses=hyps,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest apps/api/tests/test_api.py -x`
Expected: PASS (unit + GA-empty + LLM end-to-end).
If the LLM end-to-end does not reach gen ≥1 with the default stub backends, set `CAPYCHEM_PROPOSER_BACKEND=stub` / `CAPYCHEM_ANALYZER_BACKEND=stub` explicitly in the test env and/or raise `max_generations`; do NOT switch to a `direct` backend (no spend in this slice).

- [ ] **Step 6: Typecheck + lint + commit**

Run: `uv run mypy -p capychem -p capychem.api && uv run ruff check apps/api`
Expected: clean.

```bash
git add apps/api/capychem/api/schemas.py apps/api/capychem/api/routes_runs.py apps/api/tests/test_api.py
git commit -m "feat(api): serve full hypothesis sequence on RunSnapshot via DB query"
```

---

### Task 4: Web types + event reducer (`apps/web`)

Teach the snapshot type and the pure `applyEvent` reducer about hypotheses.

**Files:**
- Modify: `apps/web/lib/api.ts` (add `AnalyzerHypothesis` type; optional `hypotheses` on `RunSnapshot`)
- Modify: `apps/web/lib/runEvents.ts` (union variant + `applyEvent` case)
- Test: `apps/web/lib/runEvents.test.ts`

**Interfaces:**
- Consumes: the `analyzer.hypothesis` event payload from Task 2.
- Produces: `AnalyzerHypothesis = { after_generation_index: number; text: string; structured_json: { focus?: string; avoid?: string[] } | null }`; `RunSnapshot.hypotheses?: AnalyzerHypothesis[]`. Task 5 consumes both.

- [ ] **Step 1: Write the failing tests**

Add to `apps/web/lib/runEvents.test.ts`:

```typescript
  it("analyzer.hypothesis appends a record to hypotheses", () => {
    const next = applyEvent(base, {
      type: "analyzer.hypothesis", after_generation_index: 1, text: "h1",
      structured_json: { focus: "amide", avoid: ["phenol"] },
    });
    expect(next.hypotheses).toEqual([
      { after_generation_index: 1, text: "h1", structured_json: { focus: "amide", avoid: ["phenol"] } },
    ]);
  });
  it("analyzer.hypothesis replaces (dedups) a same-index record and stays sorted", () => {
    const seeded = {
      ...base,
      hypotheses: [
        { after_generation_index: 1, text: "old", structured_json: null },
        { after_generation_index: 3, text: "g3", structured_json: null },
      ],
    };
    const next = applyEvent(seeded, {
      type: "analyzer.hypothesis", after_generation_index: 1, text: "new", structured_json: null,
    });
    expect(next.hypotheses!.map((h) => h.after_generation_index)).toEqual([1, 3]);
    expect(next.hypotheses![0].text).toBe("new");
  });
  it("analyzer.hypothesis does not mutate the input snapshot (purity)", () => {
    const snapshot = { ...base, hypotheses: [] as NonNullable<RunSnapshot["hypotheses"]> };
    applyEvent(snapshot, {
      type: "analyzer.hypothesis", after_generation_index: 1, text: "h1", structured_json: null,
    });
    expect(snapshot.hypotheses).toEqual([]);
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm --filter web test -- --runTestsByPath lib/runEvents.test.ts`
Expected: FAIL — TypeScript/assertion error: `analyzer.hypothesis` not in the `RunEvent` union / `hypotheses` undefined.

- [ ] **Step 3: Add the type + snapshot field**

In `apps/web/lib/api.ts`, add the type and extend `RunSnapshot`:

```typescript
export type TopMolecule = { smiles: string; score: number };
export type CurvePoint = { oracle_calls: number; top10_mean: number };
export type AnalyzerHypothesis = {
  after_generation_index: number;
  text: string;
  structured_json: { focus?: string; avoid?: string[] } | null;
};
export type RunSnapshot = {
  run_id: number;
  task: string;
  status: string;
  budget: number;
  plateau_window: number;
  generation_index: number;
  oracle_calls_used: number;
  best_score: number | null;
  top_k: TopMolecule[];
  auc_curve: CurvePoint[];
  cost_so_far_usd?: number;
  hypotheses?: AnalyzerHypothesis[];
};
```

- [ ] **Step 4: Add the union variant + reducer case**

In `apps/web/lib/runEvents.ts`, import the type and extend the union + switch:

```typescript
import type { AnalyzerHypothesis, RunSnapshot, TopMolecule } from "./api";

export type RunEvent =
  | { type: "ping" }
  | {
      type: "generation.complete";
      generation_index: number;
      best_score: number;
      top10_mean: number;
      oracle_calls_used: number;
      cost_so_far_usd?: number;
      top_k: TopMolecule[];
    }
  | {
      type: "analyzer.hypothesis";
      after_generation_index: number;
      text: string;
      structured_json: { focus?: string; avoid?: string[] } | null;
    }
  | { type: "run.complete"; run_id: number; status: string; summary: unknown };
```

Add the case inside `applyEvent`'s switch (before `default`):

```typescript
    case "analyzer.hypothesis": {
      const rec: AnalyzerHypothesis = {
        after_generation_index: ev.after_generation_index,
        text: ev.text,
        structured_json: ev.structured_json,
      };
      const kept = (snap.hypotheses ?? []).filter(
        (h) => h.after_generation_index !== ev.after_generation_index,
      );
      return {
        ...snap,
        hypotheses: [...kept, rec].sort(
          (a, b) => a.after_generation_index - b.after_generation_index,
        ),
      };
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pnpm --filter web test -- --runTestsByPath lib/runEvents.test.ts`
Expected: PASS (new cases + all existing `applyEvent` tests).

- [ ] **Step 6: Typecheck + lint + commit**

Run: `pnpm --filter web typecheck && pnpm --filter web lint`
Expected: clean.

```bash
git add apps/web/lib/api.ts apps/web/lib/runEvents.ts apps/web/lib/runEvents.test.ts
git commit -m "feat(web): model analyzer.hypothesis event + hypotheses in the snapshot reducer"
```

---

### Task 5: Unified "Analyzer reasoning" section + LiveRun wiring (`apps/web`)

Render the section (newest-first, latest expanded, focus/avoid chips, empty → nothing) and wire it into `LiveRun`; hoist the carried-in `plateauNotice` double-call.

**Files:**
- Create: `apps/web/app/runs/[id]/HypothesisSection.tsx` (pure presentational component)
- Create: `apps/web/app/runs/[id]/HypothesisSection.test.tsx`
- Modify: `apps/web/app/runs/[id]/LiveRun.tsx` (render the section; hoist `plateauNotice`)

**Interfaces:**
- Consumes: `AnalyzerHypothesis` (Task 4); shadcn `Card`/`CardContent`/`CardHeader`/`CardTitle` + `Badge`.
- Produces: `HypothesisSection({ hypotheses }: { hypotheses: AnalyzerHypothesis[] })`.

- [ ] **Step 1: Write the failing test**

Create `apps/web/app/runs/[id]/HypothesisSection.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { HypothesisSection } from "./HypothesisSection";
import type { AnalyzerHypothesis } from "@/lib/api";

const hyps: AnalyzerHypothesis[] = [
  { after_generation_index: 1, text: "early signal", structured_json: { focus: "aromatic", avoid: ["ester"] } },
  { after_generation_index: 2, text: "refine amide scaffold", structured_json: { focus: "amide", avoid: ["phenol", "nitro"] } },
];

describe("HypothesisSection", () => {
  it("renders nothing when there are no hypotheses", () => {
    const { container } = render(<HypothesisSection hypotheses={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
  it("renders newest first with prose, the latest marked, and focus/avoid chips", () => {
    render(<HypothesisSection hypotheses={hyps} />);
    expect(screen.getByText("refine amide scaffold")).toBeInTheDocument();
    expect(screen.getByText(/latest/i)).toBeInTheDocument();
    expect(screen.getByText("focus: amide")).toBeInTheDocument();
    expect(screen.getByText("avoid: phenol")).toBeInTheDocument();
    expect(screen.getByText("avoid: nitro")).toBeInTheDocument();
    // newest-first ordering: gen 2 heading appears before gen 1 in the DOM
    const headings = screen.getAllByText(/After gen \d/);
    expect(headings[0]).toHaveTextContent("After gen 2");
    expect(headings[1]).toHaveTextContent("After gen 1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter web test -- --runTestsByPath app/runs/[id]/HypothesisSection.test.tsx`
Expected: FAIL — cannot resolve `./HypothesisSection`.

- [ ] **Step 3: Implement the component**

Create `apps/web/app/runs/[id]/HypothesisSection.tsx`:

```tsx
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnalyzerHypothesis } from "@/lib/api";

function Chips({ structured }: { structured: AnalyzerHypothesis["structured_json"] }) {
  if (!structured) return null;
  const focus = structured.focus;
  const avoid = structured.avoid ?? [];
  if (!focus && avoid.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {focus && <Badge variant="secondary">focus: {focus}</Badge>}
      {avoid.map((a) => (
        <Badge key={a} variant="outline">
          avoid: {a}
        </Badge>
      ))}
    </div>
  );
}

function Entry({ h, latest }: { h: AnalyzerHypothesis; latest: boolean }) {
  return (
    <details open={latest} className="rounded-md border px-3 py-2">
      <summary className="cursor-pointer text-sm font-medium">
        After gen {h.after_generation_index}
        {latest && <span className="ml-2 text-xs text-zinc-500">· latest</span>}
      </summary>
      <p className="mt-2 text-sm text-zinc-700">{h.text}</p>
      <Chips structured={h.structured_json} />
    </details>
  );
}

export function HypothesisSection({ hypotheses }: { hypotheses: AnalyzerHypothesis[] }) {
  if (hypotheses.length === 0) return null;
  const ordered = [...hypotheses].sort(
    (a, b) => b.after_generation_index - a.after_generation_index,
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Analyzer reasoning</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {ordered.map((h, i) => (
          <Entry key={h.after_generation_index} h={h} latest={i === 0} />
        ))}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter web test -- --runTestsByPath app/runs/[id]/HypothesisSection.test.tsx`
Expected: PASS.

- [ ] **Step 5: Wire into `LiveRun` + hoist `plateauNotice`**

In `apps/web/app/runs/[id]/LiveRun.tsx`:

Add the import next to the others:

```typescript
import { HypothesisSection } from "./HypothesisSection";
```

Replace the `plateauNotice` double-call block (currently lines 124-128) with a hoisted local. Insert `const notice = ...` just after `const running = !TERMINAL.has(snap.status);` (line 89), then change the JSX:

```typescript
  const running = !TERMINAL.has(snap.status);
  const notice = plateauNotice(snap.status, snap.plateau_window);
```

```tsx
      {notice && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {notice}
        </div>
      )}
```

Add the section after the "Top molecules" `Card` (after line 189, before the closing `</main>`):

```tsx
      <HypothesisSection hypotheses={snap.hypotheses ?? []} />
```

- [ ] **Step 6: Verify the full web suite + gates**

Run: `pnpm --filter web test && pnpm --filter web typecheck && pnpm --filter web lint`
Expected: all pass (including the existing `app/page.test.tsx`).

- [ ] **Step 7: Commit**

```bash
git add apps/web/app/runs/[id]/HypothesisSection.tsx apps/web/app/runs/[id]/HypothesisSection.test.tsx apps/web/app/runs/[id]/LiveRun.tsx
git commit -m "feat(web): unified Analyzer reasoning section in the run view"
```

---

### Final verification (before ship)

- [ ] **Backend gates:** `uv run pytest && uv run mypy -p capychem -p capychem.api && uv run ruff check .` — all green.
- [ ] **Frontend gates:** `pnpm --filter web test && pnpm --filter web typecheck && pnpm --filter web lint` — all green.
- [ ] **Manual live acceptance (no spend):** start the API + web, launch an `llm`-strategy run on a stub backend, open the run view, confirm `analyzer.hypothesis` arrives live (latest expands at top) and reloading the page shows the full sequence from REST; launch a `graph_ga` run and confirm the section is absent.
- [ ] Ship per `~/.claude/CLAUDE.md` (separate from this plan, post-implementation): flip slice 03 + milestone status, advance the handoff, freeze the slice doc, dated "Slice 03 shipped" log line — milestone 03 complete → milestone 04 active.

## Self-Review

**Spec coverage:**
- WS `analyzer.hypothesis` event (FR-009, SPEC §6.3) → Task 2. ✓
- Run-detail full sequence from REST (FR-011, Story 3) → Task 3 + Task 5. ✓
- Watch-live latest (Story 2) → Task 5 (latest expanded in the unified section). ✓
- Observe-don't-modify-core contract → Task 1 accumulates in state; Task 2 observes (no `RunHandle` in core). ✓
- Empty state (Graph-GA / gen 0) → Task 3 (`[]` from REST, asserted), Task 5 (renders nothing, asserted). ✓
- Dedup on GET-vs-subscribe race → Task 4 reducer (replace-by-index, asserted). ✓
- Carried-in `plateauNotice` hoist → Task 5 Step 5. ✓
- `avoid` is `list[str]`, `structured_json` may be `null` → Task 4 type + Task 5 chips handle both. ✓
- No spend / surface-only → no `direct` backend anywhere; Task 3 Step 5 forbids it. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. The one judgment note (confirm `Run(...)` required columns in Task 3 Step 1) is a verification instruction, not a placeholder.

**Type consistency:** `AnalyzerHypothesisOut` / `AnalyzerHypothesisEvent` (Python) and `AnalyzerHypothesis` (TS) share the `{after_generation_index, text, structured_json}` field set; `HypothesisRecord` (core) matches; `_hypotheses_for` returns `list[AnalyzerHypothesisOut]` consumed by `RunSnapshot.hypotheses`. The reducer stores ascending, the component renders descending — consistent and intentional.
