"""Slice 07-04b: hard constraints at the /runs boundary force exploratory, and a
malformed constraints spec (bad SMARTS / unknown catalog) is a 422.

POST /runs only enqueues (m08-02): create_run_endpoint persists the Run row
itself rather than delegating to the registry, so these tests read the row
back from a real (in-memory sqlite) session instead of stubbing
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


async def test_constraints_run_is_exploratory() -> None:
    app, sm = await _app()
    constraints = {"catalogs": ["PAINS"], "smarts_exclude": ["[N+](=O)[O-]"]}
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "constraints_json": constraints})
        assert r.status_code == 201
        run_id = r.json()["run_id"]
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row is not None
    assert row.constraints_json == constraints
    assert row.mode == "exploratory"


async def test_invalid_smarts_rejected_at_runs_boundary() -> None:
    app, sm = await _app()
    bad = {"smarts_exclude": ["not[smarts"]}
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "constraints_json": bad})
        assert r.status_code == 422
    async with sm() as s:
        rows = (await s.execute(select(Run))).scalars().all()
    assert rows == []  # never reached create_run


async def test_unknown_catalog_rejected() -> None:
    app, sm = await _app()
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "constraints_json": {"catalogs": ["BOGUS"]}})
        assert r.status_code == 422
    async with sm() as s:
        rows = (await s.execute(select(Run))).scalars().all()
    assert rows == []  # never reached create_run
