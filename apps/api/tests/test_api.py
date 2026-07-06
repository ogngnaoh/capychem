"""Integration tests for the REST + WS surface.

Real app lifespan, real Postgres, real QED scoring via the harness subprocess —
slow (~10-60 s per run) by design; httpx's ASGI WebSocket transport drives both
HTTP and WS against the in-process app.

Shared-DB caveat: each test's lifespan sweep marks stranded `running` rows
`paused` in the shared dev DB — don't run the suite while a dev server has an
active run.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from capychem.api.main import app
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_BODY = {
    "task": "qed",
    "budget": 40,
    "seed": 42,
    "pop_size": 20,
    "offspring": 10,
    "max_generations": 50,
}


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

            snap = (await c.get(f"/runs/{run_id}")).json()
            assert snap["run_id"] == run_id and snap["budget"] == 40
            assert snap["hypotheses"] == []  # graph_ga run has no analyzer hypotheses
            # server-derived mode: a plain run (no custom inputs) is benchmark (07-01)
            assert snap["mode"] == "benchmark"

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

            # Late-subscriber replay: a NEW WS on the completed run gets
            # run.complete immediately.
            async with asyncio.timeout(10):
                async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
                    msg = await ws.receive_json()
                    assert msg["type"] == "run.complete"


async def test_stop_endpoint_transitions_to_stopped() -> None:
    big = {**_BODY, "budget": 100000, "max_generations": 1000, "seed": 7}
    async with app.router.lifespan_context(app):
        async with _client() as c:
            run_id = (await c.post("/runs", json=big)).json()["run_id"]
            async with asyncio.timeout(120):
                async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
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
            # Durable partial state: snapshot of the stopped run has molecules.
            snap = (await c.get(f"/runs/{run_id}")).json()
            assert snap["status"] == "stopped" and len(snap["top_k"]) > 0


async def test_get_unknown_run_404() -> None:
    async with app.router.lifespan_context(app):
        async with _client() as c:
            assert (await c.get("/runs/99999999")).status_code == 404


async def test_ws_unknown_run_closes_4404() -> None:
    # The server accepts, then closes with 4404. httpx-ws surfaces a
    # server-initiated close as WebSocketDisconnect(code, reason) raised from
    # receive() (httpx_ws._api converts wsproto CloseConnection events). Catch
    # it INSIDE the aconnect_ws block: letting it propagate through the context
    # exit wraps it in the session task group's ExceptionGroup.
    async with app.router.lifespan_context(app):
        async with _client() as c:
            async with asyncio.timeout(10):
                async with aconnect_ws("http://test/ws/runs/99999999", c) as ws:
                    with pytest.raises(WebSocketDisconnect) as exc_info:
                        await ws.receive_json()
                    assert exc_info.value.code == 4404


async def test_compare_two_runs_and_404() -> None:
    """GET /compare wiring: two existing runs -> 200 with both runs + an
    auc_overlay list; a missing run -> 404 (the _run_snapshot None path)."""
    async with app.router.lifespan_context(app):
        async with _client() as c:
            id_a = (await c.post("/runs", json=_BODY)).json()["run_id"]
            id_b = (await c.post("/runs", json={**_BODY, "seed": 7})).json()["run_id"]
            r = await c.get(f"/compare?a={id_a}&b={id_b}")
            assert r.status_code == 200
            payload = r.json()
            assert payload["a"]["run_id"] == id_a
            assert payload["b"]["run_id"] == id_b
            assert isinstance(payload["auc_overlay"], list)
            assert (await c.get(f"/compare?a={id_a}&b=99999999")).status_code == 404


async def test_hypotheses_for_returns_rows_ordered() -> None:
    from capychem.api.routes_runs import _hypotheses_for
    from capychem.db.models import AnalyzerHypothesis, Base
    from capychem.run import RunConfig, create_run

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        run_id = await create_run(s, RunConfig(
            task="jnk3", budget=100, seed=42, pop_size=10, offspring=4,
            mutation_rate=0.01, plateau_window=5, max_generations=10,
            mutation_strategy="llm"))
    async with sm() as s:
        s.add_all([
            AnalyzerHypothesis(run_id=run_id, after_generation_index=2, text="second",
                               structured_json=None),
            AnalyzerHypothesis(run_id=run_id, after_generation_index=1, text="first",
                               structured_json={"focus": "amide", "avoid": ["phenol"]}),
        ])
        await s.commit()
        out = await _hypotheses_for(s, run_id)
    assert [h.after_generation_index for h in out] == [1, 2]
    assert out[0].text == "first"
    assert out[0].structured_json == {"focus": "amide", "avoid": ["phenol"]}
    assert out[1].structured_json is None
    await engine.dispose()


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
