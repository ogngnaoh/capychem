"""Cost aggregation + cap config (slice 4)."""

from __future__ import annotations

import pytest
from capychem.cost import cost_cap_usd, oracle_cost_so_far, record_oracle_cost
from capychem.db.models import Base, Candidate, Generation, OracleCall, Run, RunCost
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed_run_with_costs(session, costs: list[float]) -> int:
    run = Run(
        task="qed",
        budget=100,
        plateau_window=5,
        pop_size=10,
        offspring=4,
        mutation_rate=0.01,
        seed=42,
    )
    session.add(run)
    await session.flush()
    gen = Generation(run_id=run.id, index=0, proposer_used="graph_ga")
    session.add(gen)
    await session.flush()
    for c in costs:
        cand = Candidate(generation_id=gen.id, smiles="CCO", proposer="graph_ga", score=0.5)
        session.add(cand)
        await session.flush()
        session.add(
            OracleCall(
                run_id=run.id,
                candidate_id=cand.id,
                task="qed",
                score=0.5,
                wall_ms=1,
                compute_cost_usd=c,
            )
        )
    await session.commit()
    return run.id


async def test_oracle_cost_so_far_sums_calls(sm):
    async with sm() as session:
        run_id = await _seed_run_with_costs(session, [0.1, 0.2, 0.3])
        total = await oracle_cost_so_far(session, run_id)
    assert total == pytest.approx(0.6)


async def test_oracle_cost_so_far_zero_when_no_calls(sm):
    async with sm() as session:
        run_id = await _seed_run_with_costs(session, [])
        total = await oracle_cost_so_far(session, run_id)
    assert total == 0.0


async def test_record_oracle_cost_upserts(sm):
    async with sm() as session:
        run_id = await _seed_run_with_costs(session, [0.4])
        await record_oracle_cost(session, run_id, 0.4)
        await record_oracle_cost(session, run_id, 0.9)  # update, not duplicate
        rows = (
            await session.execute(RunCost.__table__.select().where(RunCost.run_id == run_id))
        ).all()
    assert len(rows) == 1
    assert rows[0].oracle_cost_usd == pytest.approx(0.9)
    assert rows[0].total_usd == pytest.approx(0.9)  # llm=0 in slice 4


async def test_record_oracle_cost_sums_llm_and_oracle(sm):
    async with sm() as session:
        run_id = await _seed_run_with_costs(session, [])
        row = await record_oracle_cost(session, run_id, 0.4, llm_usd=0.6)
    assert row.oracle_cost_usd == pytest.approx(0.4)
    assert row.llm_cost_usd == pytest.approx(0.6)
    assert row.total_usd == pytest.approx(1.0)


def test_cost_cap_default_and_override(monkeypatch):
    monkeypatch.delenv("CAPYCHEM_COST_CAP_USD", raising=False)
    assert cost_cap_usd() == 50.0
    monkeypatch.setenv("CAPYCHEM_COST_CAP_USD", "0.001")
    assert cost_cap_usd() == pytest.approx(0.001)
