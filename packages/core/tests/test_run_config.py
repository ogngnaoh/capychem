"""RunConfig threads mutation_strategy onto the Run row (slice 04)."""

from __future__ import annotations

import pytest
from capychem.db.models import Base, Run
from capychem.run import RunConfig, create_run
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _cfg(**kw):
    base = dict(
        task="qed", budget=10, seed=42, pop_size=4, offspring=4,
        mutation_rate=0.01, plateau_window=2, max_generations=1,
    )
    base.update(kw)
    return RunConfig(**base)


async def test_create_run_persists_mutation_strategy(sm) -> None:
    async with sm() as s:
        run_id = await create_run(s, _cfg(mutation_strategy="llm"))
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row.mutation_strategy == "llm"


async def test_run_config_defaults_to_graph_ga(sm) -> None:
    async with sm() as s:
        run_id = await create_run(s, _cfg())
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row.mutation_strategy == "graph_ga"
