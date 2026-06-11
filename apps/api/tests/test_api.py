"""Integration tests for the REST + WS surface.

Real app lifespan, real Postgres, real QED scoring via the harness subprocess —
slow (~10-60 s per run) by design; httpx's ASGI WebSocket transport drives both
HTTP and WS against the in-process app.

Shared-DB caveat: each test's lifespan sweep marks stranded `running` rows
`stopped` in the shared dev DB — don't run the suite while a dev server has an
active run.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from capychem.api.main import app
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

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
