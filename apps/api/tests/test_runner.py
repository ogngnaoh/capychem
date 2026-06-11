"""Integration tests for the astream-driven background runner.

Real loop, real Postgres, real QED scoring via the harness subprocess — these are
slow (~10-60 s each) by design; they prove the runner observes the unmodified
slice-2 loop end to end.
"""

from __future__ import annotations

import asyncio
from typing import Any

from capychem.api.runner import RunRegistry
from capychem.db.models import Run
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.run import RunConfig


async def test_runner_runs_to_completion_and_emits_events() -> None:
    engine = make_engine()
    await init_schema(engine)
    sm = make_sessionmaker(engine)
    reg = RunRegistry(sm)
    cfg = RunConfig(
        task="qed",
        budget=40,
        seed=42,
        pop_size=20,
        offspring=10,
        mutation_rate=0.01,
        plateau_window=5,
        max_generations=50,
    )
    run_id = await reg.start_run(cfg)

    events: list[dict[str, Any]] = []
    queue = reg.subscribe(run_id)
    # Drain events until run.complete (with a wall-clock guard).
    async with asyncio.timeout(120):
        while True:
            ev = await queue.get()
            events.append(ev)
            if ev["type"] == "run.complete":
                break

    assert any(e["type"] == "generation.complete" for e in events)
    final = events[-1]
    assert final["type"] == "run.complete"
    # Exactly-40 / status=="exhausted" is NOT guaranteed by the loop code:
    # propose_offspring may return fewer than `offspring` (crossover validity),
    # validate_batch drops invalids/duplicates, and the score node only counts
    # candidates the oracle marked valid — so a generation can score fewer calls
    # than budgeted, and the run may end via no_progress/max_generations instead.
    assert final["status"] in {"exhausted", "max_generations", "no_progress"}
    snap = reg.snapshot(run_id)
    assert snap is not None and snap["oracle_calls_used"] <= 40
    await engine.dispose()


async def test_runner_stop_halts_run() -> None:
    engine = make_engine()
    await init_schema(engine)
    sm = make_sessionmaker(engine)
    reg = RunRegistry(sm)
    cfg = RunConfig(
        task="qed",
        budget=100000,
        seed=7,
        pop_size=20,
        offspring=10,
        mutation_rate=0.01,
        plateau_window=5,
        max_generations=1000,
    )
    run_id = await reg.start_run(cfg)
    queue = reg.subscribe(run_id)
    # Wait for the first generation, then stop.
    async with asyncio.timeout(120):
        while True:
            ev = await queue.get()
            if ev["type"] == "generation.complete":
                break
        await reg.stop_run(run_id)
        while True:
            ev = await queue.get()
            if ev["type"] == "run.complete":
                assert ev["status"] == "stopped"
                break
    # The stopped run's partial state must be durable, not just in-memory:
    # finalize_run commits status + summary_json BEFORE run.complete broadcasts.
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row is not None and row.status == "stopped"
    assert row.summary_json is not None and row.summary_json["top_k"]
    await engine.dispose()
