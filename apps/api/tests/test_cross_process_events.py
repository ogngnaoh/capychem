"""Milestone 08 slice 03: cross-process live events via Postgres LISTEN/NOTIFY.

Real Postgres (LISTEN/NOTIFY is Postgres-only) -- these tests share the
apps/api/tests skip guard (Postgres + harness reachable). The dev Postgres is
SHARED across the whole suite (see test_worker_queue.py's docstring) -- a
claimable-row purge runs before each claim so an unrelated leftover row never
wins the scan instead of the run this test just created.
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx
import pytest
from capychem.api.events import RunEventPointer
from capychem.api.main import app
from capychem.api.runner import RunRegistry
from capychem.db.models import Run
from capychem.db.session import make_engine, make_sessionmaker
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy import delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


async def _purge_claimable(sm: async_sessionmaker[AsyncSession]) -> None:
    """Same purge as test_worker_queue.py: delete any pre-existing claimable
    row before a claim, so an unrelated leftover row never wins claim_next_run's
    oldest-first scan instead of the run this test creates next."""
    async with sm() as s:
        await s.execute(
            delete(Run).where(
                or_(
                    Run.status == "queued",
                    (Run.status == "running") & (Run.lease_expires_at < func.now()),
                )
            )
        )
        await s.commit()


def test_run_event_pointer_round_trips() -> None:
    ptr = RunEventPointer(run_id=7, kind="generation.complete", index=3)
    assert RunEventPointer.decode(ptr.encode()) == ptr
    terminal = RunEventPointer(run_id=7, kind="run.complete")
    assert RunEventPointer.decode(terminal.encode()) == terminal


async def test_ws_receives_events_when_run_driven_by_different_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The serving app never drives ANY run itself: no inline worker, so
    # reg.is_live(run_id) is False for this run's entire life in this process --
    # the only way generation.complete / run.complete can reach the WS is the
    # cross-process LISTEN/NOTIFY path this slice adds.
    monkeypatch.setenv("CAPYCHEM_INLINE_WORKER", "0")
    worker_engine = make_engine()
    worker_sm = make_sessionmaker(worker_engine)
    await _purge_claimable(worker_sm)
    async with app.router.lifespan_context(app):
        async with _client() as c:
            r = await c.post("/runs", json=_BODY)
            assert r.status_code == 201
            assert r.json()["status"] == "queued"
            run_id = r.json()["run_id"]

            # A SEPARATE RunRegistry -- its own engine + sessionmaker -- stands in
            # for a standalone apps/runner process: it shares only the DB, no
            # Python object, with the app serving this WS.
            worker = RunRegistry(worker_sm)
            claimed = await worker.claim_and_drive_once()
            assert claimed == run_id
            try:
                types: list[str] = []
                async with asyncio.timeout(120):
                    async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
                        while True:
                            msg = await ws.receive_json()
                            if msg["type"] == "ping":
                                continue
                            types.append(msg["type"])
                            if msg["type"] == "run.complete":
                                break
                assert "generation.complete" in types
                assert types[-1] == "run.complete"
            finally:
                handle = worker._runs.get(run_id)
                if handle is not None and handle.task is not None:
                    with contextlib.suppress(Exception):
                        await handle.task
                await worker.shutdown()
    await worker_engine.dispose()


async def test_ws_reconnect_mid_run_replays_db_snapshot_then_resumes_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPYCHEM_INLINE_WORKER", "0")
    worker_engine = make_engine()
    worker_sm = make_sessionmaker(worker_engine)
    await _purge_claimable(worker_sm)
    async with app.router.lifespan_context(app):
        async with _client() as c:
            run_id = (await c.post("/runs", json=_BODY)).json()["run_id"]

            worker = RunRegistry(worker_sm)
            claimed = await worker.claim_and_drive_once()
            assert claimed == run_id
            try:
                # First connection: read until the run is genuinely mid-flight
                # (at least one generation.complete), then disconnect. The run
                # keeps being driven by `worker` -- never live in the SERVING
                # app's own registry.
                async with asyncio.timeout(120):
                    async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws1:
                        while True:
                            msg = await ws1.receive_json()
                            if msg["type"] == "generation.complete":
                                break

                # Reconnect: a FRESH WS on the SAME still-in-flight run. Its very
                # first message must be the DB-snapshot catch-up (m08-03: "replay"),
                # and it must go on to see run.complete (m08-03: "resumes live")
                # without this run ever being live in this process.
                types: list[str] = []
                async with asyncio.timeout(120):
                    async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws2:
                        first = await ws2.receive_json()
                        assert first["type"] == "generation.complete", first
                        types.append(first["type"])
                        while types[-1] != "run.complete":
                            msg = await ws2.receive_json()
                            if msg["type"] == "ping":
                                continue
                            types.append(msg["type"])
                assert "run.complete" in types
            finally:
                handle = worker._runs.get(run_id)
                if handle is not None and handle.task is not None:
                    with contextlib.suppress(Exception):
                        await handle.task
                await worker.shutdown()
    await worker_engine.dispose()
