"""AnalyzerHypothesis table + Generation link create + persist (slice 01)."""

from __future__ import annotations

import pytest
from capychem.db.models import AnalyzerHypothesis, Base, Generation, Run
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_persist_hypothesis_and_link_generation(sm) -> None:
    async with sm() as s:
        run = Run(task="qed", budget=10, plateau_window=3, pop_size=2, offspring=2,
                  mutation_rate=0.01, seed=1)
        s.add(run)
        await s.flush()
        gen = Generation(run_id=run.id, index=1, proposer_used="llm")
        s.add(gen)
        await s.flush()
        hyp = AnalyzerHypothesis(
            run_id=run.id, after_generation_index=1, text="Focus on logP.",
            structured_json={"focus": "logP", "avoid": ["phenol"]},
            tokens_in=300, tokens_out=700, compute_cost_usd=0.0017,
        )
        s.add(hyp)
        await s.flush()
        gen.analyzer_hypothesis_id = hyp.id
        await s.commit()

    async with sm() as s:
        loaded_gen = (await s.execute(select(Generation))).scalar_one()
        loaded_hyp = (await s.execute(select(AnalyzerHypothesis))).scalar_one()
        assert loaded_gen.analyzer_hypothesis_id == loaded_hyp.id
        assert loaded_hyp.structured_json == {"focus": "logP", "avoid": ["phenol"]}
        assert loaded_hyp.after_generation_index == 1
        assert loaded_hyp.compute_cost_usd == pytest.approx(0.0017)


async def test_generation_hypothesis_id_nullable(sm) -> None:
    async with sm() as s:
        run = Run(task="qed", budget=10, plateau_window=3, pop_size=2, offspring=2,
                  mutation_rate=0.01, seed=1)
        s.add(run)
        await s.flush()
        gen = Generation(run_id=run.id, index=0, proposer_used="starting")  # gen 0: no hypothesis
        s.add(gen)
        await s.commit()
        assert gen.analyzer_hypothesis_id is None
