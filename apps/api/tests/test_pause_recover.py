"""A sustained oracle fault pauses the run recoverably instead of erroring it out,
keeping partial results durable and browsable."""

from __future__ import annotations

import pytest
from capychem.api.runner import RunRegistry
from capychem.db.models import Run
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.loop import graph as graph_mod
from capychem.oracle import HarnessError, OracleResult
from capychem.run import RunConfig


@pytest.fixture
async def sm():  # type: ignore[no-untyped-def]
    engine = make_engine()  # real Postgres (matches existing api tests)
    await init_schema(engine)
    yield make_sessionmaker(engine)
    await engine.dispose()


async def test_sustained_oracle_fault_pauses_not_errors(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Generation 0's score call succeeds (so the paused run carries real partial
    # progress); every score call from generation 1 onward raises HarnessError —
    # a sustained outage that outlasts the score node's own retry budget
    # (packages/core/capychem/loop/graph.py `_score_with_retry`).
    calls = {"n": 0}

    async def flaky_score(smiles, task):
        calls["n"] += 1
        if calls["n"] == 1:
            return [
                OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0)
                for s in smiles
            ]
        raise HarnessError("harness unavailable")

    async def instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(graph_mod, "score_batch_async", flaky_score)
    monkeypatch.setattr(graph_mod.asyncio, "sleep", instant_sleep)  # skip retry backoff delay

    registry = RunRegistry(sm)
    cfg = RunConfig(
        task="qed",
        budget=50,
        seed=42,
        pop_size=6,
        offspring=6,
        mutation_rate=0.01,
        plateau_window=3,
        max_generations=5,
    )
    run_id = await registry.start_run(cfg)
    handle = registry._runs[run_id]
    assert handle.task is not None
    await handle.task  # drive to completion

    # Terminal status is "paused", NOT "errored" — and a partial summary survives.
    assert handle.terminal_event is not None
    assert handle.terminal_event["status"] == "paused"
    assert handle.terminal_event["summary"] is not None
    assert handle.terminal_event["summary"]["generations"] == 1  # gen 0 persisted before the fault
    assert len(handle.terminal_event["summary"]["top_k"]) > 0  # gen 0's population is durable

    # Browseable: GET /runs/{id} reads the live registry snapshot first
    # (apps/api/capychem/api/routes_runs.py `_run_snapshot`), which the runner
    # updates with the terminal status before returning.
    snap = registry.snapshot(run_id)
    assert snap is not None
    assert snap["status"] == "paused"

    async with sm() as session:
        run = await session.get(Run, run_id)
    assert run is not None
    assert run.status == "paused"
    assert run.summary_json is not None
    assert run.summary_json["generations"] == 1
