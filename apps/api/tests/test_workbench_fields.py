"""RunSnapshot's workbench read-fields: valid_smiles_rate,
graph_ga_baseline, llm_cost_usd/oracle_cost_usd. All nullable/additive; exercised
against an in-memory sqlite app (no real Postgres), mirroring test_trace_link.py.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from capychem.api.ga_baseline import graph_ga_baseline
from capychem.api.routes_runs import router
from capychem.db.models import Base, Run, RunCost
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class _StubRegistry:
    """Every run is DB-only (no live overlay) — the branch these fields are read on."""

    def snapshot(self, _run_id: int) -> dict[str, Any] | None:
        return None


async def _sqlite_app(runs: list[Run], costs: list[RunCost] | None = None) -> FastAPI:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        s.add_all(runs)
        s.add_all(costs or [])
        await s.commit()
    app = FastAPI()
    app.include_router(router)
    app.state.sessionmaker = sm
    app.state.registry = _StubRegistry()
    return app


def _run(run_id: int, task: str, summary: dict[str, Any] | None) -> Run:
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
        summary_json=summary,
    )


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


# --- pure baseline lookup -----------------------------------------------------


def test_graph_ga_baseline_known_task() -> None:
    # jnk3 is a comparable row in the G1 report.
    val = graph_ga_baseline("jnk3")
    assert val == pytest.approx(0.6838650000000002)


def test_graph_ga_baseline_unbanked_task_is_none() -> None:
    # sitagliptin_mpo was not banked in the G1 sweep report.
    assert graph_ga_baseline("sitagliptin_mpo") is None


def test_graph_ga_baseline_unknown_task_is_none() -> None:
    assert graph_ga_baseline("not_a_real_task") is None


# --- RunSnapshot wiring --------------------------------------------------------


async def test_snapshot_surfaces_valid_smiles_rate_from_summary() -> None:
    summary = {
        "top_k": [],
        "oracle_calls": 80,
        "valid_smiles": {"proposed": 100, "valid": 92, "rate": 0.92, "gate": {}},
    }
    app = await _sqlite_app([_run(1, "qed", summary)])
    async with _client(app) as c:
        snap = (await c.get("/runs/1")).json()
        assert snap["valid_smiles_rate"] == pytest.approx(0.92)


async def test_snapshot_valid_smiles_rate_null_when_absent() -> None:
    app = await _sqlite_app([_run(2, "qed", {"top_k": [], "oracle_calls": 10})])
    async with _client(app) as c:
        snap = (await c.get("/runs/2")).json()
        assert snap["valid_smiles_rate"] is None


async def test_snapshot_surfaces_graph_ga_baseline_for_known_task() -> None:
    app = await _sqlite_app([_run(3, "jnk3", {"top_k": [], "oracle_calls": 10})])
    async with _client(app) as c:
        snap = (await c.get("/runs/3")).json()
        assert snap["graph_ga_baseline"] == graph_ga_baseline("jnk3")


async def test_snapshot_graph_ga_baseline_null_for_unbanked_task() -> None:
    app = await _sqlite_app([_run(4, "sitagliptin_mpo", {"top_k": [], "oracle_calls": 10})])
    async with _client(app) as c:
        snap = (await c.get("/runs/4")).json()
        assert snap["graph_ga_baseline"] is None


async def test_snapshot_surfaces_llm_and_oracle_cost_alongside_scalar() -> None:
    run = _run(5, "qed", {"top_k": [], "oracle_calls": 10})
    rc = RunCost(run_id=5, llm_cost_usd=1.25, oracle_cost_usd=0.0, total_usd=1.25)
    app = await _sqlite_app([run], [rc])
    async with _client(app) as c:
        snap = (await c.get("/runs/5")).json()
        assert snap["llm_cost_usd"] == pytest.approx(1.25)
        assert snap["oracle_cost_usd"] == pytest.approx(0.0)
        assert snap["cost_so_far_usd"] == pytest.approx(1.25)  # existing scalar unchanged


async def test_snapshot_cost_breakdown_null_when_no_runcost_row() -> None:
    app = await _sqlite_app([_run(6, "qed", {"top_k": [], "oracle_calls": 10})])
    async with _client(app) as c:
        snap = (await c.get("/runs/6")).json()
        assert snap["llm_cost_usd"] is None
        assert snap["oracle_cost_usd"] is None
        assert snap["cost_so_far_usd"] == 0.0  # existing default unchanged
