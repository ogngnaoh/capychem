"""The G1-contamination guard (milestone 07 slice 01).

The load-bearing invariant: an exploratory run must never be presented as
benchmark-comparable. Concretely, a run's snapshot carries its ``mode`` and drops
``graph_ga_baseline`` to None whenever ``mode != "benchmark"`` — even for a task
that HAS a banked Graph-GA baseline — so the UI can never render a Graph-GA "beat"
for a custom-input run. Exercised against an in-memory sqlite app + a stub
registry, mirroring test_workbench_fields.py.
"""

from __future__ import annotations

from typing import Any

import httpx
from capychem.api.ga_baseline import graph_ga_baseline
from capychem.api.routes_runs import router
from capychem.db.models import Base, Run
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class _StubRegistry:
    """Returns a fixed live snapshot dict for run_id 99, else None (DB path)."""

    def __init__(self, live: dict[str, Any] | None = None) -> None:
        self._live = live

    def snapshot(self, run_id: int) -> dict[str, Any] | None:
        return self._live if run_id == 99 else None


async def _sqlite_app(runs: list[Run], live: dict[str, Any] | None = None) -> FastAPI:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        s.add_all(runs)
        await s.commit()
    app = FastAPI()
    app.include_router(router)
    app.state.sessionmaker = sm
    app.state.registry = _StubRegistry(live)
    return app


def _run(run_id: int, *, task: str, mode: str) -> Run:
    return Run(
        id=run_id,
        task=task,
        mutation_strategy="llm",
        status="max_generations",
        budget=120,
        plateau_window=5,
        pop_size=100,
        offspring=32,
        mutation_rate=0.01,
        seed=42,
        mode=mode,
        summary_json={"top_k": [{"smiles": "CCO", "score": 0.5}], "oracle_calls": 10},
    )


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


# --- DB path: snapshot carries mode + gates the baseline ----------------------


async def test_benchmark_run_keeps_graph_ga_baseline() -> None:
    app = await _sqlite_app([_run(1, task="jnk3", mode="benchmark")])
    async with _client(app) as c:
        snap = (await c.get("/runs/1")).json()
        assert snap["mode"] == "benchmark"
        assert snap["graph_ga_baseline"] == graph_ga_baseline("jnk3")
        assert snap["graph_ga_baseline"] is not None  # jnk3 is a banked, comparable task


async def test_exploratory_run_drops_graph_ga_baseline() -> None:
    # jnk3 HAS a banked baseline; the gate must still null it because the run is
    # exploratory — proving the drop is mode-driven, not a missing-task accident.
    app = await _sqlite_app([_run(2, task="jnk3", mode="exploratory")])
    async with _client(app) as c:
        snap = (await c.get("/runs/2")).json()
        assert snap["mode"] == "exploratory"
        assert snap["graph_ga_baseline"] is None


# --- live path: same gate on the registry snapshot ----------------------------


def _live(*, task: str, mode: str) -> dict[str, Any]:
    return {
        "run_id": 99,
        "task": task,
        "status": "running",
        "budget": 120,
        "plateau_window": 5,
        "generation_index": 1,
        "oracle_calls_used": 32,
        "best_score": 0.5,
        "top_k": [{"smiles": "CCO", "score": 0.5}],
        "auc_curve": [{"oracle_calls": 32, "top10_mean": 0.4}],
        "cost_so_far_usd": 0.0,
        "mode": mode,
    }


async def test_live_benchmark_run_keeps_baseline() -> None:
    app = await _sqlite_app([], live=_live(task="jnk3", mode="benchmark"))
    async with _client(app) as c:
        snap = (await c.get("/runs/99")).json()
        assert snap["mode"] == "benchmark"
        assert snap["graph_ga_baseline"] == graph_ga_baseline("jnk3")


async def test_live_exploratory_run_drops_baseline() -> None:
    app = await _sqlite_app([], live=_live(task="jnk3", mode="exploratory"))
    async with _client(app) as c:
        snap = (await c.get("/runs/99")).json()
        assert snap["mode"] == "exploratory"
        assert snap["graph_ga_baseline"] is None


# --- list surface carries mode ------------------------------------------------


async def test_run_list_item_carries_mode() -> None:
    app = await _sqlite_app(
        [_run(1, task="jnk3", mode="benchmark"), _run(2, task="qed", mode="exploratory")]
    )
    async with _client(app) as c:
        items = (await c.get("/runs")).json()
        by_id = {i["run_id"]: i for i in items}
        assert by_id[1]["mode"] == "benchmark"
        assert by_id[2]["mode"] == "exploratory"
