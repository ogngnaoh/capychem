"""Failure recovery checks for the local scientific worker, without inference."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from capychem.experiments import worker


@pytest.mark.parametrize("failure", ["science", "generator", "exception"])
async def test_worker_retries_failed_probe_without_file_change(monkeypatch, failure):
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(worker, "make_engine", lambda: engine)
    monkeypatch.setattr(worker, "make_sessionmaker", lambda _: None)
    monkeypatch.setattr(worker, "configuration_fingerprint", lambda: "unchanged")
    heartbeat = AsyncMock()
    monkeypatch.setattr(worker, "heartbeat", heartbeat)
    calls = 0

    async def probe():
        nonlocal calls
        calls += 1
        if calls == 1 and failure == "exception":
            raise ValueError("Transient probe failure")
        return {
            "state": "unavailable" if calls == 1 and failure == "science" else "ready",
            "configuration_fingerprint": "unchanged",
            "science": {"ok": calls > 1 or failure == "generator"},
            "generator": {"configured": True, "ok": calls > 1},
        }

    async def claim(*_args):
        if calls >= 2:
            raise asyncio.CancelledError
        return None

    monkeypatch.setattr(worker, "probe_runtime", probe)
    monkeypatch.setattr(worker, "claim_next", claim)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(worker.run_forever(0.001, probe_retry_seconds=0.005), timeout=1)
    assert calls == 2
    assert any(c.args[2].get("state") == "ready" for c in heartbeat.call_args_list)
    engine.dispose.assert_awaited_once()
