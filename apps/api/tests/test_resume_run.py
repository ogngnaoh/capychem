"""06-07 Parts 2-3: a paused run continues from where it left off and reaches the
SAME terminal state an uninterrupted run would (G6-exact); the REST resume
endpoint gates on the persisted status."""

from __future__ import annotations

import asyncio
import hashlib

import httpx
import pytest
from capychem.api.main import app
from capychem.api.runner import RunRegistry
from capychem.db.models import Generation, Run
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.loop import graph as graph_mod
from capychem.oracle import HarnessError, OracleResult
from capychem.run import RunConfig
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy import select


@pytest.fixture
async def sm():  # type: ignore[no-untyped-def]
    engine = make_engine()  # real Postgres (matches existing api tests)
    await init_schema(engine)
    yield make_sessionmaker(engine)
    await engine.dispose()


def _det_score(smiles: str) -> float:
    """Deterministic, network-free stand-in oracle score: a pure function of the
    canonical SMILES, so re-scoring the same molecule -- whenever it happens, in
    whichever run -- always returns the same value (G6)."""
    digest = hashlib.sha256(smiles.encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2**32


async def _score_ok(smiles: list[str], task: str) -> list[OracleResult]:
    return [
        OracleResult(smiles=s, score=_det_score(s), valid=True, wall_ms=0, cost_usd=0.0)
        for s in smiles
    ]


async def _instant_sleep(_seconds: float) -> None:
    return None


_CFG = RunConfig(
    task="qed",
    budget=200,
    seed=42,
    pop_size=6,
    offspring=6,
    mutation_rate=0.01,
    plateau_window=20,  # high enough that plateau never wins the race vs no_progress
    max_generations=10,
    mutation_strategy="llm",
)


async def test_pause_then_resume_reaches_same_terminal_state(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    monkeypatch.setattr(graph_mod.asyncio, "sleep", _instant_sleep)

    # --- (a) an uninterrupted baseline run ---
    monkeypatch.setattr(graph_mod, "score_batch_async", _score_ok)
    registry_a = RunRegistry(sm)
    run_a = await registry_a.start_run(_CFG)
    await registry_a._runs[run_a].task
    term_a = registry_a._runs[run_a].terminal_event
    assert term_a is not None
    assert term_a["status"] not in {"paused", "errored", "cost_capped"}
    async with sm() as session:
        row_a = await session.get(Run, run_a)
    assert row_a is not None
    summary_a = row_a.summary_json
    assert summary_a is not None
    assert summary_a["generations"] >= 1  # a real trajectory, not a degenerate 0-gen run

    # --- (b) the SAME config+seed, but generation 1's score call sustains a fault:
    # the FIRST score call (generation 0) succeeds, every call after that raises
    # HarnessError -- a sustained outage that outlasts the score node's own retry
    # budget (mirrors apps/api/tests/test_pause_recover.py).
    calls = {"n": 0}

    async def _score_fault_after_gen0(smiles: list[str], task: str) -> list[OracleResult]:
        calls["n"] += 1
        if calls["n"] == 1:
            return await _score_ok(smiles, task)
        raise HarnessError("sustained outage (test)")

    monkeypatch.setattr(graph_mod, "score_batch_async", _score_fault_after_gen0)

    registry_b = RunRegistry(sm)
    run_b = await registry_b.start_run(_CFG)
    await registry_b._runs[run_b].task
    term_b = registry_b._runs[run_b].terminal_event
    assert term_b is not None
    assert term_b["status"] == "paused"

    async with sm() as session:
        row_b = await session.get(Run, run_b)
    assert row_b is not None and row_b.status == "paused"
    assert row_b.summary_json is not None
    assert row_b.summary_json["generations"] == 1  # only generation 0 persisted before the fault

    # The oracle is healthy again from here on -- the resumed drive proceeds normally.
    monkeypatch.setattr(graph_mod, "score_batch_async", _score_ok)

    await registry_b.resume_run(run_b)
    assert run_b in registry_b._runs
    await registry_b._runs[run_b].task
    term_b2 = registry_b._runs[run_b].terminal_event
    assert term_b2 is not None
    assert term_b2["status"] not in {"paused", "errored", "cost_capped"}

    async with sm() as session:
        row_b2 = await session.get(Run, run_b)
    assert row_b2 is not None
    summary_b = row_b2.summary_json
    assert summary_b is not None

    # G6: pause-then-resume reaches the SAME terminal state an uninterrupted run
    # would -- same stop reason, same unique-call count, same generation count,
    # same top-k population (smiles + score, in rank order).
    assert row_b2.status == row_a.status
    assert summary_b["oracle_calls"] == summary_a["oracle_calls"]
    assert summary_b["generations"] == summary_a["generations"]
    assert summary_b["top_k"] == summary_a["top_k"]


async def test_resume_run_rejects_a_run_that_is_not_paused(sm) -> None:  # type: ignore[no-untyped-def]
    registry = RunRegistry(sm)
    with pytest.raises(ValueError, match="not resumable"):
        await registry.resume_run(999999)  # unknown run_id


async def test_concurrent_resume_spawns_exactly_one_driver(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Two near-simultaneous resume calls (double-click / client retry) must not both
    spawn a _drive: the second is refused, so Generation.index stays unique per run
    (a duplicate would corrupt reconstruct_state)."""
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    monkeypatch.setattr(graph_mod.asyncio, "sleep", _instant_sleep)

    # Pause a run mid-flight (fault after generation 0), so it is genuinely
    # resumable (not already-terminal) — a resume WOULD drive new generations.
    calls = {"n": 0}

    async def _fault_after_gen0(smiles: list[str], task: str) -> list[OracleResult]:
        calls["n"] += 1
        if calls["n"] == 1:
            return await _score_ok(smiles, task)
        raise HarnessError("sustained outage (test)")

    monkeypatch.setattr(graph_mod, "score_batch_async", _fault_after_gen0)
    registry = RunRegistry(sm)
    run_id = await registry.start_run(_CFG)
    await registry._runs[run_id].task
    assert registry._runs[run_id].terminal_event["status"] == "paused"  # type: ignore[index]

    # Oracle healthy again; fire two resumes concurrently on the same run.
    monkeypatch.setattr(graph_mod, "score_batch_async", _score_ok)
    results = await asyncio.gather(
        registry.resume_run(run_id), registry.resume_run(run_id), return_exceptions=True
    )
    errors = [r for r in results if isinstance(r, ValueError)]
    oks = [r for r in results if not isinstance(r, BaseException)]
    assert len(errors) == 1, f"expected exactly one refusal, got {results}"
    assert len(oks) == 1
    assert "already running or resuming" in str(errors[0])

    await registry._runs[run_id].task  # let the single winning driver finish

    async with sm() as session:
        indices = (
            await session.execute(select(Generation.index).where(Generation.run_id == run_id))
        ).scalars().all()
    assert len(indices) == len(set(indices)), f"duplicate Generation.index: {sorted(indices)}"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGIWebSocketTransport(app), base_url="http://test")


_BODY = {
    "task": "qed",
    "budget": 10,
    "seed": 42,
    "pop_size": 6,
    "offspring": 6,
    "max_generations": 1,
}


async def test_resume_endpoint_rejects_non_paused_then_accepts_paused() -> None:
    async with app.router.lifespan_context(app):
        async with _client() as c:
            run_id = (await c.post("/runs", json=_BODY)).json()["run_id"]

            # Freshly created -> status "running", not "paused" -> reject.
            r = await c.post(f"/runs/{run_id}/resume")
            assert r.status_code == 409

            # Drive it to a real (small, fast) completion over the WS, then force
            # the row to "paused" -- the endpoint only cares about the persisted
            # status column, mirroring how a crash-sweep leaves a run that had
            # actually finished but never got to write its terminal status.
            async with asyncio.timeout(60):
                async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
                    while True:
                        msg = await ws.receive_json()
                        if msg["type"] == "run.complete":
                            break

            sm = app.state.sessionmaker
            async with sm() as session:
                row = await session.get(Run, run_id)
                assert row is not None
                gens_before = row.summary_json["generations"] if row.summary_json else None
                row.status = "paused"
                await session.commit()

            # This run had ALREADY completed (max_generations=1) before being forced
            # to "paused". Resuming it must FINALIZE with its terminal reason, not
            # drive a spurious extra generation (the 06-07 already-terminal guard).
            r = await c.post(f"/runs/{run_id}/resume")
            assert r.status_code == 200
            assert r.json() == {"run_id": run_id, "status": "max_generations"}

            async with sm() as session:
                row2 = await session.get(Run, run_id)
                assert row2 is not None and row2.status == "max_generations"
                # No extra generation was run on resume.
                assert row2.summary_json["generations"] == gens_before

            # No longer paused -> a second resume is rejected.
            r2 = await c.post(f"/runs/{run_id}/resume")
            assert r2.status_code == 409

            # Unknown run -> 404.
            r3 = await c.post("/runs/99999999/resume")
            assert r3.status_code == 404
