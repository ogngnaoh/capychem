"""Env-selected oracle backend + cost mapping (slice 4)."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from capychem import oracle
from capychem.oracle import OracleResult, score_batch_async


async def test_local_backend_routes_to_subprocess(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_ORACLE_BACKEND", "local")
    captured = {}

    def fake_score(smiles, task, **kw):
        captured["args"] = (tuple(smiles), task)
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=3) for s in smiles]

    monkeypatch.setattr(oracle, "score_smiles", fake_score)
    out = await score_batch_async(["CCO", "c1ccccc1"], "qed")
    assert captured["args"] == (("CCO", "c1ccccc1"), "qed")
    assert [r.cost_usd for r in out] == [0.0, 0.0]  # local is free


async def test_modal_backend_maps_payload_and_cost(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_ORACLE_BACKEND", "modal")
    monkeypatch.setenv("CAPYCHEM_ORACLE_USD_PER_SEC", "0.001")  # 0.001 $/s

    class FakeRemote:
        async def aio(self, smiles, task):
            return [{"smiles": s, "score": 0.5, "valid": True, "wall_ms": 2000} for s in smiles]

    class FakeFn:
        remote = FakeRemote()

    # patch the lookup helper, not modal itself
    monkeypatch.setattr(oracle, "_modal_score_fn", lambda: FakeFn())
    out = await score_batch_async(["CCO"], "qed")
    assert out[0].score == 0.5 and out[0].valid is True
    assert out[0].cost_usd == pytest.approx(0.002)  # 2000 ms = 2 s × 0.001 $/s


async def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_ORACLE_BACKEND", "bogus")
    with pytest.raises(ValueError, match="CAPYCHEM_ORACLE_BACKEND"):
        await score_batch_async(["CCO"], "qed")


def test_oracle_thread_pool_size_reads_env(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_ORACLE_THREAD_POOL_SIZE", "3")
    assert oracle.oracle_thread_pool_size() == 3
    monkeypatch.delenv("CAPYCHEM_ORACLE_THREAD_POOL_SIZE", raising=False)
    assert oracle.oracle_thread_pool_size() == 8  # the documented default


async def test_local_backend_routes_through_a_bounded_executor(monkeypatch):
    """A burst of concurrent score_batch_async calls must never exceed the
    injected executor's max_workers, no matter how many calls are in flight
    (milestone 08 slice 05 backpressure)."""
    monkeypatch.setenv("CAPYCHEM_ORACLE_BACKEND", "local")
    pool = ThreadPoolExecutor(max_workers=2)
    monkeypatch.setattr(oracle, "oracle_executor", lambda: pool)

    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    def slow_score(smiles, task, **kw):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.05)
        with lock:
            state["active"] -= 1
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setattr(oracle, "score_smiles", slow_score)
    try:
        await asyncio.gather(*(score_batch_async(["CCO"], "qed") for _ in range(6)))
    finally:
        pool.shutdown(wait=True)
    assert state["peak"] <= 2
    assert state["peak"] > 0  # the burst actually exercised the pool
