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

    from capychem import proposer as proposer_mod

    def _distinct_valid_stub(prompt, n, *, temperature, seed):  # type: ignore[no-untyped-def]
        # Distinct, RDKit-valid alkanes (C, CC, CCC, ...) -> no dedup loss, no fallback.
        return [
            proposer_mod.ProposalResult(
                raw="C" * (i + 1), smiles="C" * (i + 1), tokens_in=0, tokens_out=0, cost_usd=0.0
            )
            for i in range(n)
        ]

    monkeypatch.setattr(proposer_mod, "_stub_propose", _distinct_valid_stub)

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


async def test_llm_invalid_output_triggers_ga_fallback(sm, monkeypatch) -> None:
    """FR-005 end-to-end: when the LLM emits invalid SMILES, the Graph-GA fallback
    backfills the gap so the generation reaches `offspring` valid candidates and is
    recorded as 'mixed'. Harness-free: propose_offspring is monkeypatched."""
    from capychem.loop import graph as graph_mod
    from capychem.oracle import Offspring, OracleResult
    from capychem.proposer import ProposalResult

    # gen-1 LLM batch: 2 valid + 2 RDKit-invalid -> validate keeps 2 -> gap = 2.
    async def fake_llm(task, population, *, n, seed):  # type: ignore[no-untyped-def]
        smis = ["CCO", "CCN", "not_a_smiles", "J!Q"]
        return [
            ProposalResult(raw=smis[i], smiles=smis[i], tokens_in=0, tokens_out=0, cost_usd=0.0)
            for i in range(n)
        ]

    # GA fallback returns 2 distinct valid offspring (no harness).
    def fake_offspring(population, n_offspring, *, mutation_rate, seed, **kw):  # type: ignore[no-untyped-def]
        pool = ["CCCC", "CCCCC", "CCCCCC"]
        return [Offspring(smiles=pool[i], parents=(0, 1)) for i in range(n_offspring)]

    async def fake_score(smiles, task):  # type: ignore[no-untyped-def]
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0) for s in smiles
        ]

    monkeypatch.setattr(graph_mod.strategy, "propose_llm_async", fake_llm)
    monkeypatch.setattr(graph_mod.strategy, "propose_offspring", fake_offspring)
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
    assert final["done"] is True

    from sqlalchemy import select

    async with sm() as s:
        gens = (await s.execute(select(Generation.proposer_used))).scalars().all()
        cand_proposers = set((await s.execute(select(Candidate.proposer))).scalars().all())
    # gen-1 fired the fallback -> recorded "mixed", with BOTH origins among candidates.
    assert "mixed" in gens
    assert {"llm", "graph_ga"} <= cand_proposers
