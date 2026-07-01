"""Trace deep-link (FR-014 / SPEC §6.3 `GET /trace/{run_id}`).

The app persists each run's Langfuse trace id in `summary_json["trace_id"]`
(no schema change — `summary_json` is an existing JSON column). The deep link
is built from `LANGFUSE_HOST` + `LANGFUSE_PROJECT_ID`; when either the project
is unconfigured or the run has no trace id, there is simply no link (graceful).

Core URL logic is a pure function (`config.trace_url`); the route + the snapshot
field are exercised against an in-memory sqlite app (no real Postgres).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from capychem.api import config
from capychem.api.routes_runs import router
from capychem.db.models import Base, Run
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_HOST = "http://localhost:3001"
_PID = "cmqfcuo9w0006t9iw7ommzmjx"
_TID = "a1c0ec65-732a-4e13-80c6-81df514d75e1"


# --- pure URL logic ----------------------------------------------------------


def test_trace_url_builds_deep_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", _HOST)
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", _PID)
    assert config.trace_url(_TID) == f"{_HOST}/project/{_PID}/traces/{_TID}"


def test_trace_url_strips_trailing_slash_on_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", _HOST + "/")
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", _PID)
    assert config.trace_url(_TID) == f"{_HOST}/project/{_PID}/traces/{_TID}"


def test_trace_url_none_when_project_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", _HOST)
    monkeypatch.delenv("LANGFUSE_PROJECT_ID", raising=False)
    assert config.trace_url(_TID) is None


def test_trace_url_none_when_no_trace_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", _HOST)
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", _PID)
    assert config.trace_url(None) is None


# --- route + snapshot against an in-memory sqlite app ------------------------


class _StubRegistry:
    """Every run is DB-only (no live overlay), so the snapshot/detail paths read
    summary_json — the branch the trace link lives on."""

    def snapshot(self, _run_id: int) -> dict[str, Any] | None:
        return None


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
    app.state.registry = _StubRegistry()
    return app


def _run(run_id: int, summary: dict[str, Any] | None) -> Run:
    return Run(
        id=run_id, task="qed", mutation_strategy="llm", status="max_generations",
        budget=120, plateau_window=5, pop_size=100, offspring=32, mutation_rate=0.01,
        seed=42, summary_json=summary,
    )


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_get_trace_returns_deep_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", _HOST)
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", _PID)
    app = await _sqlite_app([_run(271, {"top_k": [], "oracle_calls": 80, "trace_id": _TID})])
    async with _client(app) as c:
        r = await c.get("/trace/271")
        assert r.status_code == 200
        assert r.json()["trace_url"] == f"{_HOST}/project/{_PID}/traces/{_TID}"


async def test_get_trace_unknown_run_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", _PID)
    app = await _sqlite_app([])
    async with _client(app) as c:
        assert (await c.get("/trace/999999")).status_code == 404


async def test_get_trace_null_when_no_trace_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", _HOST)
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", _PID)
    app = await _sqlite_app([_run(5, {"top_k": [], "oracle_calls": 40})])  # no trace_id
    async with _client(app) as c:
        r = await c.get("/trace/5")
        assert r.status_code == 200 and r.json()["trace_url"] is None


async def test_snapshot_carries_trace_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", _HOST)
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", _PID)
    app = await _sqlite_app([_run(271, {"top_k": [], "oracle_calls": 80, "trace_id": _TID})])
    async with _client(app) as c:
        snap = (await c.get("/runs/271")).json()
        assert snap["trace_url"] == f"{_HOST}/project/{_PID}/traces/{_TID}"
