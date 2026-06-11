# Web Surface (Slice 3 `02-web-surface`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A browser-driven local run — launch a QED optimization from a Next.js form, watch it advance live over a WebSocket, and stop it early — backed by FastAPI REST + WS hosting the shipped slice-2 LangGraph loop as an in-process background task.

**Architecture:** FastAPI gains a `RunRegistry` of in-process background `asyncio` tasks. Each task drives the existing `build_graph(sessionmaker).astream(...)` (the slice-2 loop is **observed, never modified**), updating a per-run in-memory snapshot and fanning `generation.complete`/`run.complete` events out to WebSocket clients; stop = a cancel `asyncio.Event` the driver checks at generation boundaries. The Next.js app gets a shadcn launch form and a live page that loads a REST snapshot then subscribes to the WS. Run-row create/finalize logic is extracted to `capychem.run` and shared by the CLI and the API (DRY).

**Tech Stack:** FastAPI 0.115 + uvicorn, async SQLAlchemy (existing), LangGraph `astream`, httpx (ASGI test client) + a WS test client; Next.js 16 / React 19 / TS 5 / Tailwind v4 + shadcn/ui; vitest + Playwright.

**Design doc:** `docs/superpowers/specs/2026-06-11-web-surface-design.md` (read it before starting).

**Ground rules (from CLAUDE.md — do not violate):**
- NEVER `import` from `harness/` in `packages/` or `apps/`. The runner reaches the oracle only through the existing loop → `oracle.py` subprocess.
- The slice-2 loop code under `packages/core/capychem/loop/` MUST remain unchanged (exit criterion). Refactoring `cli.py` (not in `loop/`) is allowed.
- Validate every SMILES via RDKit before persistence (already enforced inside the loop; the API adds no new SMILES path in this slice).
- Frontend talks to FastAPI via the **absolute** API origin for WebSockets; never proxy WS through Next.js middleware (CLAUDE.md gotcha).
- `mypy -p capychem` strict + `ruff check packages apps/api` + `ruff format --check packages apps/api` stay green on all new Python; `pnpm --filter web typecheck/lint/build` stay green on all new TS.
- Commit frequently, one logical change per commit, on `main` (the main-flow branch for this slice; no worktree requested).
- Commit message trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

**Pre-flight:** Postgres up (`docker compose -f infra/compose.yml up -d`); harness venv present (`test -x harness/.venv/bin/python`); `pnpm install` done. The slice-2 loop + CLI are shipped and green.

---

## File Structure

Core (`packages/core/capychem/`):
- `run.py` — NEW: `RunConfig` dataclass + `create_run(session, config) -> int` + `finalize_run(session, run_id, final_state)`; shared by CLI + API (DRY extraction).
- `cli.py` — MODIFY: use `capychem.run` helpers (behavior unchanged).

Backend (`apps/api/capychem/api/`):
- `schemas.py` — NEW: Pydantic request/response models (`CreateRunRequest`, `RunSnapshot`, event payloads).
- `runner.py` — NEW: `RunHandle`, `RunRegistry`, `start_run`, the `astream` driver task.
- `routes_runs.py` — NEW: `POST /runs`, `GET /runs/{id}`, `POST /runs/{id}/stop`.
- `ws_runs.py` — NEW: `GET /ws/runs/{id}` + heartbeat.
- `main.py` — MODIFY: lifespan (engine/sessionmaker/init_schema), mount routers + WS, `/healthz` Postgres check.
- `pyproject.toml` — MODIFY: no runtime deps added (fastapi has WS via starlette); test deps go in the root dev group.

Frontend (`apps/web/`):
- `lib/api.ts` — NEW: typed REST client + WS URL helper.
- `lib/runEvents.ts` — NEW: pure reducer `applyEvent(state, event)` (unit-tested).
- `components/ui/*` — shadcn primitives (generated).
- `app/page.tsx` — MODIFY: launch form.
- `app/runs/[id]/page.tsx` — NEW: live view.
- `app/runs/[id]/LiveRun.tsx` — NEW: client component (snapshot + WS + chart + stop).
- test config: `vitest.config.ts`, `playwright.config.ts`, `lib/runEvents.test.ts`, `e2e/launch.spec.ts`.

Config / infra:
- root `pyproject.toml` — MODIFY: dev deps (`httpx`, `httpx-ws`).
- `apps/web/package.json` — MODIFY: shadcn + recharts + vitest + playwright deps + scripts.
- `.env.example` — already has `NEXT_PUBLIC_API_URL`; no change.
- `scripts/smoke.sh` — MODIFY: API `/healthz` + `pnpm --filter web build` checks.

---

## Task 1: Shared run-config + lifecycle helpers (`capychem.run`), refactor CLI

DRY: both the CLI and the API create a `Run` row from a config and finalize it from the loop's final state. Extract once.

**Files:**
- Create: `packages/core/capychem/run.py`
- Modify: `packages/core/capychem/cli.py`
- Test: `packages/core/tests/test_run_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from capychem.run import RunConfig, create_run, finalize_run
from capychem.db.session import make_engine, make_sessionmaker, init_schema
from capychem.db.models import Run


async def test_create_and_finalize_run() -> None:
    engine = make_engine()
    await init_schema(engine)
    sm = make_sessionmaker(engine)
    cfg = RunConfig(task="qed", budget=40, seed=42, pop_size=20, offspring=10,
                    mutation_rate=0.01, plateau_window=5, max_generations=50)
    async with sm() as s:
        run_id = await create_run(s, cfg)
        assert isinstance(run_id, int)
    async with sm() as s:
        await finalize_run(s, run_id, {"stop_reason": "exhausted",
                                       "summary": {"top_k": [], "generations": 3}})
    async with sm() as s:
        row = await s.get(Run, run_id)
        assert row is not None and row.status == "exhausted"
        assert row.summary_json == {"top_k": [], "generations": 3}
    await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest packages/core/tests/test_run_helpers.py -v` → FAIL (`No module named 'capychem.run'`).

- [ ] **Step 3: Write `capychem/run.py`**

```python
"""Run-row config + lifecycle helpers, shared by the CLI and the API.

Keeps the Run row's create/finalize logic in one place so the CLI driver and the
FastAPI background runner agree on column population and terminal status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from capychem.db.models import Run


@dataclass(frozen=True)
class RunConfig:
    task: str
    budget: int
    seed: int
    pop_size: int
    offspring: int
    mutation_rate: float
    plateau_window: int
    max_generations: int


async def create_run(session: AsyncSession, config: RunConfig) -> int:
    """Insert a Run row (status='running') and return its id."""
    row = Run(
        task=config.task,
        budget=config.budget,
        mutation_strategy="graph_ga",
        plateau_window=config.plateau_window,
        pop_size=config.pop_size,
        offspring=config.offspring,
        mutation_rate=config.mutation_rate,
        seed=config.seed,
        status="running",
    )
    session.add(row)
    await session.commit()
    return row.id


async def finalize_run(
    session: AsyncSession, run_id: int, final_state: dict[str, Any]
) -> None:
    """Set terminal status + summary_json from the loop's final state."""
    row = await session.get(Run, run_id)
    if row is None:  # defensive; the row was just created by us
        return
    row.status = final_state.get("stop_reason") or "exhausted"
    row.summary_json = final_state.get("summary")
    await session.commit()
```

- [ ] **Step 4: Refactor `cli.py` to use the helpers.** Replace the inline `Run(...)` insert block with `run_id = await create_run(session, RunConfig(task=args.task, budget=args.budget, seed=args.seed, pop_size=args.pop_size, offspring=args.offspring, mutation_rate=args.mutation_rate, plateau_window=args.plateau_window, max_generations=args.max_generations))`, and replace the final status/summary block with `await finalize_run(session, run_id, final)`. Add `from capychem.run import RunConfig, create_run, finalize_run`; remove the now-unused `Run` import if orphaned. Keep everything else (graph build, ainvoke, trace, print) identical.

- [ ] **Step 5: Verify** — `uv run pytest packages/core/tests/test_run_helpers.py packages/core/tests/test_cli_e2e.py -q` (the e2e test proves the CLI still works through the refactor), then `uv run mypy -p capychem && uv run ruff check packages && uv run ruff format --check packages`. All green.

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/run.py packages/core/capychem/cli.py packages/core/tests/test_run_helpers.py
git commit -m "refactor(slice3): extract RunConfig + create_run/finalize_run; CLI reuses them

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: API test deps + app lifespan + `/healthz` Postgres check

**Files:**
- Modify: root `pyproject.toml` (`[dependency-groups].dev`)
- Modify: `apps/api/capychem/api/main.py`

- [ ] **Step 1: Add test deps.** In root `pyproject.toml` `dev` list add `"httpx>=0.27"` and `"httpx-ws>=0.6"` (ASGI REST client + WS test client). Run `uv sync`.

- [ ] **Step 2: Rewrite `main.py` with a lifespan + healthz DB check** (routers/WS are mounted in later tasks — leave the mount lines as TODO-free placeholders by importing them once those modules exist; for THIS task, wire only lifespan + healthz):

```python
"""CapyChem FastAPI backend — REST + WebSocket host for the in-process loop."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from capychem.db.session import init_schema, make_engine, make_sessionmaker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = make_engine()
    await init_schema(engine)
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="CapyChem API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    engine = app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    return {"status": "ok"}
```

- [ ] **Step 3: Verify import + healthz** — `uv run python -c "from capychem.api.main import app; print('ok')"` and `uv run mypy -p capychem && uv run ruff check apps/api && uv run ruff format --check apps/api`. Then a quick live check: `uv run uvicorn capychem.api.main:app --port 8001 &` … `curl -fsS localhost:8001/healthz` → `{"status":"ok"}` … kill it. (Postgres must be up.)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock apps/api/capychem/api/main.py
git commit -m "feat(slice3): FastAPI lifespan (engine/sessionmaker/init_schema) + healthz DB check

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: Pydantic schemas (request/response + event payloads)

**Files:**
- Create: `apps/api/capychem/api/schemas.py`

- [ ] **Step 1: Write `schemas.py`**

```python
"""Pydantic models for the REST + WS surface (request bodies, snapshot, events)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    task: str = "qed"
    budget: int = Field(gt=0)  # FR-015
    seed: int = 42
    pop_size: int = Field(default=100, gt=1)  # crossover needs two parents
    offspring: int = Field(default=32, gt=0)
    mutation_rate: float = 0.01
    plateau_window: int = 5
    max_generations: int = Field(default=100, gt=0)


class TopMolecule(BaseModel):
    smiles: str
    score: float


class CurvePoint(BaseModel):
    oracle_calls: int
    top10_mean: float


class RunSnapshot(BaseModel):
    run_id: int
    task: str
    status: str
    budget: int
    generation_index: int
    oracle_calls_used: int
    best_score: float | None
    top_k: list[TopMolecule]
    auc_curve: list[CurvePoint]


class GenerationCompleteEvent(BaseModel):
    type: Literal["generation.complete"] = "generation.complete"
    generation_index: int
    best_score: float
    oracle_calls_used: int
    top_k: list[TopMolecule]


class RunCompleteEvent(BaseModel):
    type: Literal["run.complete"] = "run.complete"
    run_id: int
    status: str
    summary: dict[str, Any] | None
```

- [ ] **Step 2: Verify** — `uv run python -c "from capychem.api.schemas import CreateRunRequest, RunSnapshot; print('ok')"`; `uv run mypy -p capychem && uv run ruff check apps/api && uv run ruff format --check apps/api`.

- [ ] **Step 3: Commit**

```bash
git add apps/api/capychem/api/schemas.py
git commit -m "feat(slice3): pydantic schemas — CreateRunRequest, RunSnapshot, WS events

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: RunRegistry + background runner (astream driver, broadcaster, cancel)

The heart of the slice. Observes the loop via `astream`, keeps a per-run snapshot, broadcasts events, and cancels at generation boundaries.

**Files:**
- Create: `apps/api/capychem/api/runner.py`
- Test: `apps/api/tests/test_runner.py` (create `apps/api/tests/` dir)

- [ ] **Step 1: Write the failing test** (real harness QED + Postgres; drives a tiny run to completion and asserts events + snapshot)

```python
from __future__ import annotations

import asyncio

from capychem.api.runner import RunRegistry
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.run import RunConfig


async def test_runner_runs_to_completion_and_emits_events() -> None:
    engine = make_engine()
    await init_schema(engine)
    sm = make_sessionmaker(engine)
    reg = RunRegistry(sm)
    cfg = RunConfig(task="qed", budget=40, seed=42, pop_size=20, offspring=10,
                    mutation_rate=0.01, plateau_window=5, max_generations=50)
    run_id = await reg.start_run(cfg)

    events: list[dict] = []
    queue = reg.subscribe(run_id)
    # Drain events until run.complete (with a wall-clock guard).
    async with asyncio.timeout(120):
        while True:
            ev = await queue.get()
            events.append(ev)
            if ev["type"] == "run.complete":
                break

    assert any(e["type"] == "generation.complete" for e in events)
    final = events[-1]
    assert final["type"] == "run.complete" and final["status"] in {"exhausted", "max_generations", "no_progress"}
    snap = reg.snapshot(run_id)
    assert snap is not None and snap["oracle_calls_used"] <= 40
    await engine.dispose()


async def test_runner_stop_halts_run() -> None:
    engine = make_engine()
    await init_schema(engine)
    sm = make_sessionmaker(engine)
    reg = RunRegistry(sm)
    cfg = RunConfig(task="qed", budget=100000, seed=7, pop_size=20, offspring=10,
                    mutation_rate=0.01, plateau_window=5, max_generations=1000)
    run_id = await reg.start_run(cfg)
    queue = reg.subscribe(run_id)
    # Wait for the first generation, then stop.
    async with asyncio.timeout(120):
        while True:
            ev = await queue.get()
            if ev["type"] == "generation.complete":
                break
        await reg.stop_run(run_id)
        while True:
            ev = await queue.get()
            if ev["type"] == "run.complete":
                assert ev["status"] == "stopped"
                break
    await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest apps/api/tests/test_runner.py -v` → FAIL (no module). (Add `apps/api/tests/__init__.py` is NOT needed; pytest rootdir discovery works — but ensure `apps/api/tests/` is collected: see Task 6 Step 2 for pytest config; for now run with the explicit path.)

- [ ] **Step 3: Write `runner.py`**

```python
"""In-process background runner: drives the slice-2 loop via astream.

One asyncio task per run. The task consumes ``graph.astream(stream_mode="values")``,
updates a per-run snapshot, broadcasts generation.complete / run.complete to
subscribed asyncio.Queues, and stops at a generation boundary when the run's
cancel Event is set. The loop code itself is never modified — we only observe it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from capychem.loop.graph import build_graph
from capychem.loop.state import LoopState
from capychem.run import RunConfig, create_run, finalize_run


def _snapshot_from_state(run_id: int, cfg: RunConfig, state: dict[str, Any]) -> dict[str, Any]:
    pop = state.get("population", [])
    top = sorted(pop, key=lambda m: (-m.score, m.smiles))[:10]
    curve = state.get("auc_curve", [])
    return {
        "run_id": run_id,
        "task": cfg.task,
        "status": "running",
        "budget": cfg.budget,
        "generation_index": state.get("gen_index", 0),
        "oracle_calls_used": state.get("calls_used", 0),
        "best_score": (top[0].score if top else None),
        "top_k": [{"smiles": m.smiles, "score": m.score} for m in top],
        "auc_curve": [{"oracle_calls": c, "top10_mean": v} for c, v in curve],
    }


@dataclass
class RunHandle:
    run_id: int
    config: RunConfig
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    snapshot: dict[str, Any] | None = None
    task: asyncio.Task[None] | None = None

    def broadcast(self, event: dict[str, Any]) -> None:
        for q in list(self.subscribers):
            q.put_nowait(event)


class RunRegistry:
    """Owns the live runs. Single-process, single event loop (MVP)."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker
        self._runs: dict[int, RunHandle] = {}

    async def start_run(self, config: RunConfig) -> int:
        async with self._sm() as session:
            run_id = await create_run(session, config)
        handle = RunHandle(run_id=run_id, config=config)
        self._runs[run_id] = handle
        handle.task = asyncio.create_task(self._drive(handle))
        return run_id

    def subscribe(self, run_id: int) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        handle = self._runs.get(run_id)
        if handle is not None:
            handle.subscribers.add(q)
        return q

    def unsubscribe(self, run_id: int, q: asyncio.Queue[dict[str, Any]]) -> None:
        handle = self._runs.get(run_id)
        if handle is not None:
            handle.subscribers.discard(q)

    def snapshot(self, run_id: int) -> dict[str, Any] | None:
        handle = self._runs.get(run_id)
        return handle.snapshot if handle is not None else None

    def is_live(self, run_id: int) -> bool:
        return run_id in self._runs

    async def stop_run(self, run_id: int) -> bool:
        handle = self._runs.get(run_id)
        if handle is None:
            return False
        handle.cancel.set()
        return True

    async def _drive(self, handle: RunHandle) -> None:
        cfg = handle.config
        graph = build_graph(self._sm)
        initial: LoopState = {
            "run_id": handle.run_id, "task": cfg.task, "budget": cfg.budget,
            "seed": cfg.seed, "pop_size": cfg.pop_size, "offspring": cfg.offspring,
            "mutation_rate": cfg.mutation_rate, "plateau_window": cfg.plateau_window,
            "max_generations": cfg.max_generations, "calls_used": 0, "gen_index": 0,
            "population": [], "run_span_id": None, "gen_span_id": None,
            "auc_curve": [], "done": False,
        }
        recursion_limit = cfg.max_generations * 6 + 10
        last_curve_len = 0
        final_state: dict[str, Any] = {}
        stopped = False
        stream = graph.astream(initial, config={"recursion_limit": recursion_limit},
                               stream_mode="values")
        try:
            async for state in stream:
                final_state = state
                if len(state.get("auc_curve", [])) > last_curve_len:
                    last_curve_len = len(state["auc_curve"])
                    handle.snapshot = _snapshot_from_state(handle.run_id, cfg, state)
                    snap = handle.snapshot
                    handle.broadcast({
                        "type": "generation.complete",
                        "generation_index": snap["generation_index"],
                        "best_score": snap["best_score"] if snap["best_score"] is not None else 0.0,
                        "oracle_calls_used": snap["oracle_calls_used"],
                        "top_k": snap["top_k"],
                    })
                    if handle.cancel.is_set():
                        stopped = True
                        break
        finally:
            await stream.aclose()

        status = "stopped" if stopped else (final_state.get("stop_reason") or "exhausted")
        summary = final_state.get("summary")
        async with self._sm() as session:
            await finalize_run(session, handle.run_id,
                               {"stop_reason": status, "summary": summary})
        handle.broadcast({"type": "run.complete", "run_id": handle.run_id,
                          "status": status, "summary": summary})
        # Keep the handle briefly so late subscribers can read the terminal snapshot,
        # then drop it. For MVP simplicity we leave it in the registry; GET falls back
        # to the DB once it's gone (Task 5).
```

Notes for the implementer: `graph.astream` on the installed langgraph 1.2.x yields the full state dict each super-step with `stream_mode="values"`. A generation completes when `auc_curve` grows (the `persist` node appended a point). Stopping breaks at that boundary — `persist` has committed and `stop_check` has run, so the DB is consistent. If `astream`'s kwarg/stream-mode name differs in the installed version, confirm via `uv run python -c "from capychem.loop.graph import build_graph; help(build_graph.__wrapped__)"` or the langgraph docs and adjust minimally; the contract (observe per-generation state, cancel at boundary) stays the same. If mypy flags `state` as `Any`/`dict`, annotate `state: dict[str, Any]` in the loop.

- [ ] **Step 4: Run the tests** — `uv run pytest apps/api/tests/test_runner.py -v` → 2 PASS (takes ~10-30 s; real QED). If `test_runner_stop_halts_run` hangs, confirm the cancel check runs at the generation boundary and `astream` actually yields between generations.

- [ ] **Step 5: Typecheck/lint + commit** — `uv run mypy -p capychem && uv run ruff check apps/api && uv run ruff format --check apps/api`.

```bash
git add apps/api/capychem/api/runner.py apps/api/tests/test_runner.py
git commit -m "feat(slice3): RunRegistry + astream-driven background runner (events + cooperative stop)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 5: REST routes — POST /runs, GET /runs/{id}, POST /runs/{id}/stop

**Files:**
- Create: `apps/api/capychem/api/routes_runs.py`
- Modify: `apps/api/capychem/api/main.py` (instantiate the registry in lifespan; include the router)

- [ ] **Step 1: Write `routes_runs.py`**

```python
"""REST routes for runs: create, snapshot, stop."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from capychem.api.runner import RunRegistry
from capychem.api.schemas import CreateRunRequest, RunSnapshot
from capychem.db.models import Run
from capychem.run import RunConfig

router = APIRouter()


def _registry(request: Request) -> RunRegistry:
    reg: RunRegistry = request.app.state.registry
    return reg


@router.post("/runs", status_code=201)
async def create_run_endpoint(body: CreateRunRequest, request: Request) -> dict[str, Any]:
    cfg = RunConfig(
        task=body.task, budget=body.budget, seed=body.seed, pop_size=body.pop_size,
        offspring=body.offspring, mutation_rate=body.mutation_rate,
        plateau_window=body.plateau_window, max_generations=body.max_generations,
    )
    run_id = await _registry(request).start_run(cfg)
    return {"run_id": run_id, "status": "running"}


@router.get("/runs/{run_id}", response_model=RunSnapshot)
async def get_run_endpoint(run_id: int, request: Request) -> RunSnapshot:
    reg = _registry(request)
    live = reg.snapshot(run_id)
    if live is not None:
        return RunSnapshot(**live)
    # Terminal / not-in-registry: read the DB.
    sm = request.app.state.sessionmaker
    async with sm() as session:
        row = await session.get(Run, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        summary = row.summary_json or {}
        top = summary.get("top_k", [])
        curve = summary.get("auc_curve", [])
        return RunSnapshot(
            run_id=row.id, task=row.task, status=row.status, budget=row.budget,
            generation_index=summary.get("generations", 0),
            oracle_calls_used=summary.get("oracle_calls", 0),
            best_score=(top[0]["score"] if top else None),
            top_k=top, auc_curve=curve,
        )


@router.post("/runs/{run_id}/stop")
async def stop_run_endpoint(run_id: int, request: Request) -> dict[str, Any]:
    ok = await _registry(request).stop_run(run_id)
    if not ok:
        # Either unknown or already terminal — treat as idempotent no-op if the row exists.
        sm = request.app.state.sessionmaker
        async with sm() as session:
            row = await session.get(Run, run_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return {"run_id": run_id, "status": "stopping"}
    return {"run_id": run_id, "status": "stopping"}
```

- [ ] **Step 2: Wire the registry + router in `main.py`.** In the lifespan, after creating the sessionmaker, add `from capychem.api.runner import RunRegistry` and `app.state.registry = RunRegistry(app.state.sessionmaker)`. After the `app = FastAPI(...)` + CORS, add `from capychem.api.routes_runs import router as runs_router` and `app.include_router(runs_router)`. (Place imports at module top per ruff.)

- [ ] **Step 3: Verify** — `uv run python -c "from capychem.api.main import app; print([r.path for r in app.routes])"` shows `/runs`, `/runs/{run_id}`, `/runs/{run_id}/stop`. `uv run mypy -p capychem && uv run ruff check apps/api && uv run ruff format --check apps/api`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/capychem/api/routes_runs.py apps/api/capychem/api/main.py
git commit -m "feat(slice3): REST routes — POST /runs, GET /runs/{id} snapshot, POST /stop

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 6: WebSocket endpoint + heartbeat + backend integration tests

**Files:**
- Create: `apps/api/capychem/api/ws_runs.py`
- Modify: `apps/api/capychem/api/main.py` (include WS router)
- Create: `apps/api/tests/test_api.py`
- Modify: root `pyproject.toml` `[tool.pytest.ini_options]` (collect `apps/api/tests`)

- [ ] **Step 1: Write `ws_runs.py`**

```python
"""WebSocket: /ws/runs/{id}. Pushes run events; heartbeats to keep the socket warm.

Snapshot-on-load is the REST GET's job; the WS streams only NEW events. A run that
is already terminal at connect time gets a single run.complete (from the DB) and a
close, so a late client isn't left hanging.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from capychem.api.runner import RunRegistry
from capychem.db.models import Run

router = APIRouter()

_HEARTBEAT_S = 15.0


@router.websocket("/ws/runs/{run_id}")
async def ws_run(websocket: WebSocket, run_id: int) -> None:
    await websocket.accept()
    reg: RunRegistry = websocket.app.state.registry
    if not reg.is_live(run_id):
        # Already terminal (or never live in this process): send a final event + close.
        sm = websocket.app.state.sessionmaker
        async with sm() as session:
            row = await session.get(Run, run_id)
        if row is None:
            await websocket.close(code=4404)
            return
        await websocket.send_json({"type": "run.complete", "run_id": run_id,
                                   "status": row.status, "summary": row.summary_json})
        await websocket.close()
        return

    queue = reg.subscribe(run_id)
    try:
        while True:
            try:
                event: dict[str, Any] = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_S)
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json(event)
            if event["type"] == "run.complete":
                break
    except WebSocketDisconnect:
        pass
    finally:
        reg.unsubscribe(run_id, queue)
```

- [ ] **Step 2: Include the WS router + configure pytest collection.** In `main.py` add `from capychem.api.ws_runs import router as ws_router` and `app.include_router(ws_router)`. In root `pyproject.toml`, under `[tool.pytest.ini_options]` (exists from slice 2 with `asyncio_mode="auto"`), add `testpaths = ["packages/core/tests", "apps/api/tests"]`.

- [ ] **Step 3: Write `test_api.py`** (httpx ASGI transport for REST; httpx-ws for the socket)

```python
from __future__ import annotations

import asyncio

import httpx
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from capychem.api.main import app

_BODY = {"task": "qed", "budget": 40, "seed": 42, "pop_size": 20,
         "offspring": 10, "max_generations": 50}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGIWebSocketTransport(app), base_url="http://test")


async def test_post_runs_rejects_nonpositive_budget() -> None:
    async with app.router.lifespan_context(app):
        async with _client() as c:
            r = await c.post("/runs", json={**_BODY, "budget": 0})
            assert r.status_code == 422  # pydantic gt=0


async def test_create_then_snapshot_then_complete_over_ws() -> None:
    async with app.router.lifespan_context(app):
        async with _client() as c:
            r = await c.post("/runs", json=_BODY)
            assert r.status_code == 201
            run_id = r.json()["run_id"]

            # snapshot endpoint returns a valid shape while/after running
            snap = (await c.get(f"/runs/{run_id}")).json()
            assert snap["run_id"] == run_id and snap["budget"] == 40

            types: list[str] = []
            async with asyncio.timeout(120):
                async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
                    while True:
                        msg = await ws.receive_json()
                        if msg["type"] == "ping":
                            continue
                        types.append(msg["type"])
                        if msg["type"] == "run.complete":
                            assert msg["status"] in {"exhausted", "max_generations", "no_progress"}
                            break
            assert "generation.complete" in types


async def test_stop_endpoint_transitions_to_stopped() -> None:
    big = {**_BODY, "budget": 100000, "max_generations": 1000, "seed": 7}
    async with app.router.lifespan_context(app):
        async with _client() as c:
            run_id = (await c.post("/runs", json=big)).json()["run_id"]
            async with asyncio.timeout(120):
                async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
                    # wait for first generation, then stop
                    while True:
                        msg = await ws.receive_json()
                        if msg["type"] == "generation.complete":
                            break
                    assert (await c.post(f"/runs/{run_id}/stop")).status_code == 200
                    while True:
                        msg = await ws.receive_json()
                        if msg["type"] == "run.complete":
                            assert msg["status"] == "stopped"
                            break


async def test_get_unknown_run_404() -> None:
    async with app.router.lifespan_context(app):
        async with _client() as c:
            assert (await c.get("/runs/99999999")).status_code == 404
```

- [ ] **Step 4: Run the backend tests** — `uv run pytest apps/api/tests -v` → all PASS (a couple run the real loop; ~30-60 s total). If `httpx_ws` import fails, confirm `httpx-ws` is in the dev group (Task 2) and `uv sync` ran.

- [ ] **Step 5: Typecheck/lint + commit** — `uv run mypy -p capychem && uv run ruff check apps/api && uv run ruff format --check apps/api`.

```bash
git add apps/api/capychem/api/ws_runs.py apps/api/capychem/api/main.py apps/api/tests/test_api.py pyproject.toml
git commit -m "feat(slice3): WS /ws/runs/{id} + heartbeat; REST+WS integration tests

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 7: Frontend — shadcn/ui setup + API client + event reducer

**Files:**
- Modify: `apps/web/package.json` (deps + scripts)
- Create: shadcn config + `components/ui/{button,input,card,table,label}.tsx` (generated)
- Create: `apps/web/lib/api.ts`, `apps/web/lib/runEvents.ts`

- [ ] **Step 1: Install deps + shadcn.** From `apps/web/`: `pnpm add recharts` and dev tooling `pnpm add -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @playwright/test`. Then init shadcn (Tailwind v4 + Next 16): `pnpm dlx shadcn@latest init -d` and add primitives `pnpm dlx shadcn@latest add button input label card table badge`. If the non-interactive flags differ in the installed shadcn, run it and accept defaults (New York / zinc / CSS variables). Confirm `components/ui/*` exist and `app/globals.css` gained the shadcn tokens. Add scripts to `package.json`: `"test": "vitest run"`, `"test:e2e": "playwright test"`.

- [ ] **Step 2: Write `lib/api.ts`**

```ts
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TopMolecule = { smiles: string; score: number };
export type CurvePoint = { oracle_calls: number; top10_mean: number };
export type RunSnapshot = {
  run_id: number; task: string; status: string; budget: number;
  generation_index: number; oracle_calls_used: number; best_score: number | null;
  top_k: TopMolecule[]; auc_curve: CurvePoint[];
};
export type CreateRunBody = {
  task: string; budget: number; seed: number; pop_size: number;
  offspring: number; mutation_rate: number; max_generations: number;
};

export async function createRun(body: CreateRunBody): Promise<{ run_id: number }> {
  const r = await fetch(`${API_URL}/runs`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `HTTP ${r.status}`);
  return r.json();
}

export async function getRun(id: number): Promise<RunSnapshot> {
  const r = await fetch(`${API_URL}/runs/${id}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function stopRun(id: number): Promise<void> {
  await fetch(`${API_URL}/runs/${id}/stop`, { method: "POST" });
}

export function wsUrl(id: number): string {
  return `${API_URL.replace(/^http/, "ws")}/ws/runs/${id}`;
}
```

- [ ] **Step 3: Write `lib/runEvents.ts`** (pure reducer — unit-tested in Task 10)

```ts
import type { RunSnapshot, TopMolecule } from "./api";

export type RunEvent =
  | { type: "ping" }
  | { type: "generation.complete"; generation_index: number; best_score: number;
      oracle_calls_used: number; top_k: TopMolecule[] }
  | { type: "run.complete"; run_id: number; status: string; summary: unknown };

export function applyEvent(snap: RunSnapshot, ev: RunEvent): RunSnapshot {
  switch (ev.type) {
    case "ping":
      return snap;
    case "generation.complete":
      return {
        ...snap,
        generation_index: ev.generation_index,
        oracle_calls_used: ev.oracle_calls_used,
        best_score: ev.best_score,
        top_k: ev.top_k,
        auc_curve: [...snap.auc_curve,
          { oracle_calls: ev.oracle_calls_used, top10_mean: ev.best_score }],
      };
    case "run.complete":
      return { ...snap, status: ev.status };
  }
}
```

- [ ] **Step 4: Verify** — `pnpm --filter web typecheck` and `pnpm --filter web lint` green.

- [ ] **Step 5: Commit**

```bash
git add apps/web/package.json apps/web/pnpm-lock.yaml apps/web/components.json apps/web/components apps/web/lib apps/web/app/globals.css
git commit -m "feat(slice3): shadcn/ui setup + typed API client + run-event reducer

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(Note: pnpm lockfile may be at repo root — `git add` the actual lockfile path that changed.)

---

## Task 8: Frontend — launch page (`app/page.tsx`)

**Files:**
- Modify: `apps/web/app/page.tsx`

- [ ] **Step 1: Replace `page.tsx` with the launch form** (shadcn `Card`/`Input`/`Label`/`Button`; client component; validates + submits → redirect)

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createRun } from "@/lib/api";

const DEFAULTS = { budget: 200, seed: 42, pop_size: 100, offspring: 32,
  mutation_rate: 0.01, max_generations: 100 };

export default function Home() {
  const router = useRouter();
  const [form, setForm] = useState(DEFAULTS);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const num = (k: keyof typeof DEFAULTS) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: Number(e.target.value) });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (form.budget <= 0) return setError("Budget must be a positive integer.");
    if (form.pop_size <= 1) return setError("Population size must be greater than 1.");
    setBusy(true);
    try {
      const { run_id } = await createRun({ task: "qed", ...form });
      router.push(`/runs/${run_id}`);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-6 p-8">
      <Card>
        <CardHeader><CardTitle>Launch a QED optimization</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="grid grid-cols-2 gap-4">
            {([
              ["budget", "Oracle-call budget"], ["seed", "Seed"],
              ["pop_size", "Population size"], ["offspring", "Offspring / gen"],
              ["mutation_rate", "Mutation rate"], ["max_generations", "Max generations"],
            ] as const).map(([k, label]) => (
              <div key={k} className="flex flex-col gap-1">
                <Label htmlFor={k}>{label}</Label>
                <Input id={k} type="number" step="any" value={form[k]} onChange={num(k)} />
              </div>
            ))}
            <div className="col-span-2 flex items-center justify-between">
              {error && <span className="text-sm text-red-600">{error}</span>}
              <Button type="submit" disabled={busy} className="ml-auto">
                {busy ? "Starting…" : "Start run"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
```

- [ ] **Step 2: Verify** — `pnpm --filter web typecheck && pnpm --filter web lint`. Manual (optional): `pnpm --filter web dev` + start the API, fill the form, confirm it redirects to `/runs/{id}`.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/page.tsx
git commit -m "feat(slice3): launch form — POST /runs then redirect to live view

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 9: Frontend — live view (`app/runs/[id]/`)

**Files:**
- Create: `apps/web/app/runs/[id]/page.tsx` (server component shell)
- Create: `apps/web/app/runs/[id]/LiveRun.tsx` (client: snapshot + WS + chart + stop)

- [ ] **Step 1: Write the page shell** `app/runs/[id]/page.tsx`

```tsx
import { LiveRun } from "./LiveRun";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <LiveRun runId={Number(id)} />;
}
```

- [ ] **Step 2: Write `LiveRun.tsx`** (snapshot-on-load, then subscribe; chart via recharts; stop button; heartbeat-driven connection indicator)

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getRun, stopRun, wsUrl, type RunSnapshot } from "@/lib/api";
import { applyEvent, type RunEvent } from "@/lib/runEvents";

const TERMINAL = new Set(["exhausted", "max_generations", "no_progress", "stopped", "errored"]);

export function LiveRun({ runId }: { runId: number }) {
  const [snap, setSnap] = useState<RunSnapshot | null>(null);
  const [conn, setConn] = useState<"connecting" | "live" | "done">("connecting");
  const snapRef = useRef<RunSnapshot | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    getRun(runId).then((s) => {
      if (closed) return;
      snapRef.current = s; setSnap(s);
      if (TERMINAL.has(s.status)) { setConn("done"); return; }
      ws = new WebSocket(wsUrl(runId));
      ws.onopen = () => setConn("live");
      ws.onmessage = (e) => {
        const ev: RunEvent = JSON.parse(e.data);
        if (ev.type === "ping") return;
        const next = applyEvent(snapRef.current!, ev);
        snapRef.current = next; setSnap(next);
        if (ev.type === "run.complete") setConn("done");
      };
      ws.onclose = () => setConn((c) => (c === "live" ? "done" : c));
    });
    return () => { closed = true; ws?.close(); };
  }, [runId]);

  if (!snap) return <main className="p-8">Loading run {runId}…</main>;
  const running = !TERMINAL.has(snap.status);

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Run {snap.run_id} · {snap.task}</h1>
        <div className="flex items-center gap-3">
          <Badge variant={running ? "default" : "secondary"}>{snap.status}</Badge>
          <span className="text-xs text-zinc-500">{conn}</span>
          {running && <Button size="sm" variant="destructive" onClick={() => stopRun(runId)}>Stop</Button>}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Stat label="Generation" value={String(snap.generation_index)} />
        <Stat label="Oracle calls" value={`${snap.oracle_calls_used} / ${snap.budget}`} />
        <Stat label="Best score" value={snap.best_score?.toFixed(4) ?? "—"} />
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm">Top-10 mean vs oracle calls</CardTitle></CardHeader>
        <CardContent className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={snap.auc_curve}>
              <XAxis dataKey="oracle_calls" /><YAxis domain={[0, 1]} />
              <Line type="monotone" dataKey="top10_mean" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">Top molecules</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow><TableHead>#</TableHead><TableHead>SMILES</TableHead><TableHead>Score</TableHead></TableRow></TableHeader>
            <TableBody>
              {snap.top_k.map((m, i) => (
                <TableRow key={m.smiles}>
                  <TableCell>{i + 1}</TableCell>
                  <TableCell className="font-mono text-xs">{m.smiles}</TableCell>
                  <TableCell>{m.score.toFixed(4)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card><CardContent className="pt-6">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
    </CardContent></Card>
  );
}
```

- [ ] **Step 3: Verify** — `pnpm --filter web typecheck && pnpm --filter web lint && pnpm --filter web build`. Manual (optional): with API + web running, launch a run and watch counters/chart/table update live; click Stop and confirm status → `stopped`.

- [ ] **Step 4: Commit**

```bash
git add apps/web/app/runs
git commit -m "feat(slice3): live run view — snapshot + WS updates, AUC chart, top-K, stop

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 10: Frontend tests — vitest reducer/form + Playwright smoke

**Files:**
- Create: `apps/web/vitest.config.ts`, `apps/web/lib/runEvents.test.ts`
- Create: `apps/web/playwright.config.ts`, `apps/web/e2e/launch.spec.ts`

- [ ] **Step 1: `vitest.config.ts`**

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", globals: true },
});
```

- [ ] **Step 2: `lib/runEvents.test.ts`** (pure reducer — no network)

```ts
import { describe, expect, it } from "vitest";
import { applyEvent } from "./runEvents";
import type { RunSnapshot } from "./api";

const base: RunSnapshot = {
  run_id: 1, task: "qed", status: "running", budget: 100,
  generation_index: 0, oracle_calls_used: 0, best_score: null,
  top_k: [], auc_curve: [],
};

describe("applyEvent", () => {
  it("ping is a no-op", () => {
    expect(applyEvent(base, { type: "ping" })).toBe(base);
  });
  it("generation.complete updates counters, top_k, and appends a curve point", () => {
    const next = applyEvent(base, {
      type: "generation.complete", generation_index: 1, best_score: 0.7,
      oracle_calls_used: 20, top_k: [{ smiles: "CCO", score: 0.7 }],
    });
    expect(next.generation_index).toBe(1);
    expect(next.oracle_calls_used).toBe(20);
    expect(next.best_score).toBe(0.7);
    expect(next.auc_curve).toEqual([{ oracle_calls: 20, top10_mean: 0.7 }]);
  });
  it("run.complete sets terminal status", () => {
    const next = applyEvent(base, { type: "run.complete", run_id: 1, status: "stopped", summary: null });
    expect(next.status).toBe("stopped");
  });
});
```

- [ ] **Step 3: Run reducer test** — `pnpm --filter web test` → 3 pass.

- [ ] **Step 4: `playwright.config.ts` + `e2e/launch.spec.ts`** (happy path; assumes API + web are up — the test starts the web dev server; the API must be running with Postgres + harness)

```ts
// playwright.config.ts
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  webServer: { command: "pnpm dev", url: "http://localhost:3000", reuseExistingServer: true },
  use: { baseURL: "http://localhost:3000" },
});
```

```ts
// e2e/launch.spec.ts
import { expect, test } from "@playwright/test";

test("launch a run and reach a terminal state", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Oracle-call budget").fill("40");
  await page.getByLabel("Population size").fill("20");
  await page.getByLabel("Offspring / gen").fill("10");
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page).toHaveURL(/\/runs\/\d+/);
  // The status badge eventually reaches a terminal state.
  await expect(page.getByText(/exhausted|max_generations|no_progress|stopped/)).toBeVisible({ timeout: 120000 });
});
```

- [ ] **Step 5: Run Playwright** (API must be up: `uv run uvicorn capychem.api.main:app --port 8000` + Postgres + harness). `pnpm --filter web exec playwright install --with-deps chromium` then `pnpm --filter web test:e2e`. Expect 1 pass. If the environment can't run a browser, document it as a manual check and skip in CI (note it; don't fake it).

- [ ] **Step 6: Verify gates + commit** — `pnpm --filter web typecheck && pnpm --filter web lint`.

```bash
git add apps/web/vitest.config.ts apps/web/lib/runEvents.test.ts apps/web/playwright.config.ts apps/web/e2e apps/web/package.json apps/web/pnpm-lock.yaml
git commit -m "test(slice3): vitest reducer tests + Playwright launch smoke

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 11: Smoke-script + final gate + slice-shipping docs

**Files:**
- Modify: `scripts/smoke.sh`
- Modify: `docs/00-walking-skeleton/milestone.md` (slice status flip)
- Modify: `docs/00-walking-skeleton/handoff.md` (overwrite)
- Create + freeze: `docs/00-walking-skeleton/02-web-surface.md`

- [ ] **Step 1: Extend `scripts/smoke.sh`.** Add, after the existing web-lint check, a backend-API import + web-build check:
```bash
check "api imports" uv run python -c "from capychem.api.main import app"
check "web build" pnpm --filter web build
```
(Keep the loop e2e check from slice 2. The API-up `/healthz` curl is exercised by the backend tests already; the import check is a cheap smoke.)

- [ ] **Step 2: Full green gate.** Run:
```bash
uv run pytest packages/core/tests apps/api/tests -q
uv run mypy -p capychem
uv run ruff check packages apps/api
uv run ruff format --check packages apps/api
pnpm --filter web typecheck && pnpm --filter web lint && pnpm --filter web build && pnpm --filter web test
scripts/smoke.sh
```
All green; smoke ends `== N passed, 0 failed ==`. Do not proceed until green.

- [ ] **Step 3: Verify exit criteria** (design doc §8) against reality:
  - Launch → live page → counters/top-K/chart update live → terminal state (Playwright smoke + manual).
  - Stop halts a run → `status="stopped"`, partial state via `GET /runs/{id}` (backend test asserts).
  - Reload mid-run shows correct snapshot then resumes (manual; the snapshot path is unit-covered by `GET` test).
  - Two concurrent runs don't interfere (optional manual: launch two, both progress).
  - No `import` from `harness/` in `apps/`: `grep -rn "import.*harness\|from harness\|capychem_harness" apps` → only path-strings/docstrings, no imports.
  - Loop code unchanged: `git diff <slice2-ship-sha>..HEAD -- packages/core/capychem/loop/` → empty.

- [ ] **Step 4: Author + freeze the slice doc** `docs/00-walking-skeleton/02-web-surface.md` (Goal / Plan (files touched) / Tasks (this checklist, ticked) / Notes (deferrals: run-list, run-detail w/ 2D, compare, RunCost, Modal)). Mark status shipped.

- [ ] **Step 5: Flip milestone + overwrite handoff** (one commit, per CLAUDE.md "when a slice ships"):
  - `milestone.md` Slices list: `02-web-surface` → shipped (2026-..); advance `03-cloudify` as next.
  - `handoff.md` overwrite (20–40 lines): Completed this session (slice 3 + commit refs); Slice status (`02-web-surface` → shipped); Current state (branch `main`, browser-driven local run works); **Next session start here** = slice 4 (`03-cloudify`): Modal-hosted oracle worker; API swaps local subprocess for Modal; RunCost wiring + cost gate; WS cold-start heartbeat already present from this slice; Active concerns (Langfuse enabled-path still unverified; Playwright browser availability in CI).

- [ ] **Step 6: Ship commit**

```bash
git add scripts/smoke.sh docs/00-walking-skeleton/
git commit -m "docs(slice3): ship 02-web-surface — flip milestone/handoff, freeze slice doc

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review notes (verify before executing)

- **Spec coverage:** §2 decisions all have tasks — stop control (Tasks 4-6, 9), snapshot-on-load (Tasks 5, 9), SMILES+score+curve display (Tasks 5, 9), shadcn (Task 7), WS heartbeat (Task 6). §4 architecture (RunRegistry/astream runner Task 4; REST Task 5; WS Task 6; frontend Tasks 7-9). §7 testing (backend Task 6; frontend Task 10). §8 exit criteria (Task 11).
- **FR coverage:** FR-001 (launch config, Task 8/5), FR-002 (budget — inherited from the loop), FR-009 (live WS updates, Tasks 6/9), FR-015 (refuse bad config — Task 3 pydantic + Task 8 client). Deferred: FR-003/005/007 (loop-level, prior slices/milestones), FR-010/011/012/013/014 (list/detail/compare/cost/trace-link → milestone 04).
- **Loop-code-unchanged invariant:** the runner uses `astream`; no task edits `packages/core/capychem/loop/`. Task 1 edits `cli.py` (allowed — not under `loop/`). Task 11 Step 3 verifies the loop diff is empty.
- **Type consistency:** `RunConfig` fields (Task 1) match `CreateRunRequest` (Task 3) and the runner's `initial` LoopState (Task 4) and `RunSnapshot`/`getRun` (Tasks 3,7,9). The WS event shapes (Task 4 broadcast / Task 3 schema / Task 7 `RunEvent` / Task 10 test) all agree: `generation.complete{generation_index,best_score,oracle_calls_used,top_k}`, `run.complete{run_id,status,summary}`, `ping`.
- **Known soft spots to watch during execution (flagged, not blocking):**
  1. `graph.astream` kwarg / `stream_mode="values"` shape on the installed langgraph 1.2.x — confirm it yields full-state dicts per super-step; adjust the generation-boundary detection if the yield granularity differs (Task 4 note).
  2. `httpx-ws` ASGI transport + `app.router.lifespan_context` is the lifespan-in-test idiom; if the installed httpx/httpx-ws differ, use `asgi-lifespan`'s `LifespanManager` instead (Task 6).
  3. shadcn init under Tailwind v4 + Next 16 may prompt; run interactively or with the current non-interactive flags and accept defaults (Task 7).
  4. Playwright needs a browser binary + the API running; if the sandbox can't, mark the e2e as a documented manual check (don't fake a pass) (Task 10 Step 5).
  5. pnpm lockfile path (root vs `apps/web`) — `git add` whichever actually changed (Tasks 7, 10).
