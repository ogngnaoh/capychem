"""Slice 07-06: GET /runs/{id}/manifest returns the citable provenance manifest."""

from __future__ import annotations

import httpx
from capychem.api.routes_runs import router
from capychem.db.models import Base, Run
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def _sqlite_app(runs: list[Run]) -> FastAPI:
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
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def _run(run_id: int, manifest: dict | None) -> Run:
    return Run(
        id=run_id, task="qed", mutation_strategy="graph_ga", status="exhausted", budget=100,
        plateau_window=5, pop_size=10, offspring=4, mutation_rate=0.01, seed=42,
        mode="benchmark", manifest_json=manifest,
    )


async def test_manifest_round_trips() -> None:
    manifest = {"git_sha": "abc1234", "model_id": "deepseek-v4-pro", "pytdc_version": "0.3.6"}
    app = await _sqlite_app([_run(1, manifest)])
    async with _client(app) as c:
        r = await c.get("/runs/1/manifest")
        assert r.status_code == 200
        assert r.json() == manifest


async def test_manifest_404_for_unknown_run() -> None:
    app = await _sqlite_app([])
    async with _client(app) as c:
        assert (await c.get("/runs/999/manifest")).status_code == 404


async def test_manifest_endpoint_end_to_end() -> None:
    """A real run's finalize writes a manifest with the real PyTDC pin + model id +
    git SHA. Uses the shared dev Postgres + harness (slow)."""
    import asyncio

    from capychem.api.main import app as real_app
    from httpx_ws import aconnect_ws
    from httpx_ws.transport import ASGIWebSocketTransport

    body = {
        "task": "qed", "budget": 100, "seed": 42, "pop_size": 4, "offspring": 4,
        "max_generations": 1, "mutation_strategy": "graph_ga",
    }
    async with real_app.router.lifespan_context(real_app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(real_app), base_url="http://test"
        ) as c:
            run_id = (await c.post("/runs", json=body)).json()["run_id"]
            async with asyncio.timeout(120):
                async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
                    while True:
                        if (await ws.receive_json())["type"] == "run.complete":
                            break
            manifest = (await c.get(f"/runs/{run_id}/manifest")).json()
    assert manifest["pytdc_version"] == "0.3.6"  # the real harness pin
    assert manifest["model_id"]  # proposer.llm_model()
    assert manifest["git_sha"]  # a real commit SHA
    assert manifest["config"]["task"] == "qed"
