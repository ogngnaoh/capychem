"""Gate-purity: valid_smiles in summary_json counts the LLM proposer only.

Drives the real graph with a fake scorer (no harness). Non-LLM runs (graph_ga /
starting seeds) must omit the valid_smiles block entirely; LLM runs must report
only LLM-proposed SMILES (gen-0 seeds excluded).
"""

from __future__ import annotations

import pytest
from capychem.db.models import Base
from capychem.loop import graph as graph_mod
from capychem.loop.state import LoopState
from capychem.oracle import OracleResult
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_graph_ga_run_omits_valid_smiles_block(sm, monkeypatch):
    # The >80% gate is an LLM-validity concept. A graph_ga run (gen-0 "starting"
    # seeds + graph_ga offspring) has no LLM proposals, so summary_json must NOT
    # carry a valid_smiles block (previously it reported an inflated ~100%).
    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0) for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    from capychem.run import RunConfig, create_run

    cfg = RunConfig(
        task="qed",
        budget=12,
        seed=42,
        pop_size=4,
        offspring=4,
        mutation_rate=0.01,
        plateau_window=2,
        max_generations=2,
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
        "calls_used": 0,
        "gen_index": 0,
        "population": [],
        "run_trace_id": None,
        "gen_span_id": None,
        "auc_curve": [],
        "done": False,
    }
    final = await g.ainvoke(initial, config={"recursion_limit": 30})
    assert "valid_smiles" not in final["summary"]


async def test_llm_run_reports_llm_only_valid_rate(sm, monkeypatch):
    # Gen-1 LLM proposes 4 (2 valid + 2 invalid); gen-0 seeds are all valid.
    # The block must reflect LLM-only validity: proposed=4, valid=2, rate=0.5
    # (gen-0 seeds excluded; fallback fills never enter _validation_stats).
    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0) for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)

    from capychem.loop import strategy
    from capychem.proposer import ProposalResult

    async def fake_llm(task, population, *, n, seed, hypothesis=None):
        smis = ["CCO", "c1ccccc1", "not-a-smiles", "@@@@"]
        return [
            ProposalResult(raw=smis[i % 4], smiles=smis[i % 4], tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    monkeypatch.setattr(strategy, "propose_llm_async", fake_llm)
    from capychem.run import RunConfig, create_run

    cfg = RunConfig(
        task="qed",
        budget=12,
        seed=42,
        pop_size=4,
        offspring=4,
        mutation_rate=0.01,
        plateau_window=2,
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
    final = await g.ainvoke(initial, config={"recursion_limit": 30})
    vs = final["summary"]["valid_smiles"]
    assert vs["proposed"] == 4
    assert vs["valid"] == 2
    assert vs["rate"] == 0.5
