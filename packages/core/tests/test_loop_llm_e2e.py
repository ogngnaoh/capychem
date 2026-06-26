"""End-to-end: a mutation_strategy='llm' run completes on the stub backend (slice 04)."""

from __future__ import annotations

import pytest
from capychem.db.models import Base, Candidate, Generation
from capychem.loop import graph as graph_mod
from capychem.loop.state import LoopState
from capychem.oracle import OracleResult
from capychem.run import RunConfig, create_run
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_llm_run_completes_end_to_end(sm, monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")  # network-free, all-valid

    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0) for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)

    cfg = RunConfig(
        task="qed",
        budget=50,
        seed=42,
        pop_size=6,
        offspring=4,
        mutation_rate=0.01,
        plateau_window=3,
        max_generations=2,
        mutation_strategy="llm",
    )
    async with sm() as s:
        run_id = await create_run(s, cfg)
    g = graph_mod.build_graph(sm)
    initial: LoopState = {
        "run_id": run_id,
        "task": cfg.task,
        "budget": cfg.budget,
        "seed": cfg.seed,
        "pop_size": cfg.pop_size,
        "offspring": cfg.offspring,
        "mutation_rate": cfg.mutation_rate,
        "plateau_window": cfg.plateau_window,
        "max_generations": cfg.max_generations,
        "mutation_strategy": "llm",
        "calls_used": 0,
        "gen_index": 0,
        "population": [],
        "run_trace_id": None,
        "gen_span_id": None,
        "auc_curve": [],
        "done": False,
    }
    final = await g.ainvoke(initial, config={"recursion_limit": 40})

    # 1. Completed end-to-end with a summary.
    assert final["done"] is True
    assert final["summary"]["generations"] >= 1
    # 2. valid_smiles + gate present (gen 1 ran the LLM; stub pool is all valid -> PASS).
    gate = final["summary"]["valid_smiles"]["gate"]
    assert gate["passed"] is True
    # 3. Provenance: a generation produced by the LLM is recorded as such.
    async with sm() as s:
        gens = (await s.execute(select(Generation.proposer_used))).scalars().all()
        cand_proposers = set((await s.execute(select(Candidate.proposer))).scalars().all())
    assert "llm" in gens
    assert "llm" in cand_proposers
