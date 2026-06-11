"""The runner trips a clean cost_capped termination over the dollar cap."""

from __future__ import annotations

import pytest
from capychem import cost as cost_mod
from capychem.api.runner import RunRegistry
from capychem.db.models import Run, RunCost
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.run import RunConfig
from sqlalchemy import select


@pytest.fixture
async def sm():  # type: ignore[no-untyped-def]
    engine = make_engine()  # real Postgres (matches existing api tests)
    await init_schema(engine)
    yield make_sessionmaker(engine)
    await engine.dispose()


async def test_cost_cap_trips_cost_capped(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Force the aggregated cost above the default $50 cap on the first boundary.
    async def fake_total(session: object, run_id: int) -> float:
        return 999.0

    monkeypatch.setattr(cost_mod, "oracle_cost_so_far", fake_total)

    registry = RunRegistry(sm)
    cfg = RunConfig(
        task="qed",
        budget=8,
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

    assert handle.terminal_event is not None
    assert handle.terminal_event["status"] == "cost_capped"
    async with sm() as session:
        run = await session.get(Run, run_id)
        rc = await session.scalar(select(RunCost).where(RunCost.run_id == run_id))
    assert run is not None and run.status == "cost_capped"
    assert rc is not None and rc.total_usd == pytest.approx(999.0)
