"""Slice 07-04: a composed objective at the /runs boundary forces exploratory, and
POST /objective/validate previews the composite (structural 422 on a bad spec).

POST /runs only enqueues (m08-02): create_run_endpoint persists the Run row
itself rather than delegating to the registry, so the run-creating tests read
the row back from a real (in-memory sqlite) session instead of stubbing
RunRegistry.start_run to capture an in-memory RunConfig.
"""

from __future__ import annotations

import httpx
from capychem.api.routes_runs import router
from capychem.db.models import Base, Run
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def _app() -> tuple[FastAPI, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(router)
    app.state.sessionmaker = sm
    app.state.registry = None  # inline_worker_enabled=False below -> never touched
    app.state.inline_worker_enabled = False
    return app, sm


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


_BODY = {"task": "qed", "budget": 40, "seed": 42, "pop_size": 20, "offspring": 10}

_QED_OBJECTIVE = {
    "terms": [{"oracle": "qed", "weight": 1.0, "transform": {"kind": "identity"}}],
    "aggregator": "weighted_sum",
}


async def test_objective_run_is_exploratory() -> None:
    app, sm = await _app()
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "objective_json": _QED_OBJECTIVE})
        assert r.status_code == 201
        run_id = r.json()["run_id"]
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row is not None
    assert row.objective_json == _QED_OBJECTIVE
    assert row.mode == "exploratory"


async def test_invalid_objective_rejected_at_runs_boundary() -> None:
    app, sm = await _app()
    bad = {"terms": [{"oracle": "nonexistent", "weight": 1.0}], "aggregator": "weighted_sum"}
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "objective_json": bad})
        assert r.status_code == 422
    async with sm() as s:
        rows = (await s.execute(select(Run))).scalars().all()
    assert rows == []  # never reached create_run


async def test_objective_validate_previews_composite() -> None:
    app, _ = await _app()
    async with _client(app) as c:
        r = await c.post(
            "/objective/validate", json={"spec": _QED_OBJECTIVE, "smiles": ["CCO", "not-a-smiles"]}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["n_terms"] == 1
        by_smi = {x["smiles"]: x["score"] for x in body["results"]}
        assert by_smi["CCO"] is not None and 0.0 <= by_smi["CCO"] <= 1.0
        assert by_smi["not-a-smiles"] is None  # invalid -> penalized/None


async def test_objective_validate_rejects_bad_spec() -> None:
    app, _ = await _app()
    async with _client(app) as c:
        r = await c.post(
            "/objective/validate",
            json={"spec": {"terms": [], "aggregator": "weighted_sum"}, "smiles": ["CCO"]},
        )
        assert r.status_code == 422


async def test_composed_objective_run_completes_end_to_end() -> None:
    """Full glue against the real app: a 2-term composed objective (PMO qed + RDKit
    qed descriptor) runs the loop to completion, is exploratory, and every top-K score
    is a single [0,1] scalar. Uses the shared dev Postgres + harness (slow)."""
    import asyncio

    from capychem.api.main import app as real_app
    from httpx_ws import aconnect_ws
    from httpx_ws.transport import ASGIWebSocketTransport

    objective = {
        "terms": [
            {"oracle": "pmo", "oracle_kwargs": {"task": "qed"}, "weight": 1.0,
             "transform": {"kind": "identity"}},
            {"oracle": "qed", "weight": 1.0, "transform": {"kind": "identity"}},
        ],
        "aggregator": "weighted_sum",
    }
    body = {
        "task": "qed", "budget": 100, "seed": 42, "pop_size": 4, "offspring": 4,
        "max_generations": 1, "mutation_strategy": "graph_ga", "objective_json": objective,
    }
    async with real_app.router.lifespan_context(real_app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(real_app), base_url="http://test"
        ) as c:
            run_id = (await c.post("/runs", json=body)).json()["run_id"]
            async with asyncio.timeout(120):
                async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
                    while True:
                        msg = await ws.receive_json()
                        if msg["type"] == "run.complete":
                            break
            snap = (await c.get(f"/runs/{run_id}")).json()
    assert snap["mode"] == "exploratory"
    assert snap["top_k"] and all(0.0 <= m["score"] <= 1.0 for m in snap["top_k"])
