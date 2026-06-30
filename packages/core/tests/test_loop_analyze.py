"""The analyze node: runs for llm gen>=1, persists + links, threads, falls back."""

from __future__ import annotations

import pytest
from capychem.analyzer import AnalyzerResult
from capychem.db.models import AnalyzerHypothesis, Base, Generation
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


def _initial(run_id: int, cfg: RunConfig) -> LoopState:
    return {
        "run_id": run_id, "task": cfg.task, "budget": cfg.budget, "seed": cfg.seed,
        "pop_size": cfg.pop_size, "offspring": cfg.offspring, "mutation_rate": cfg.mutation_rate,
        "plateau_window": cfg.plateau_window, "max_generations": cfg.max_generations,
        "mutation_strategy": cfg.mutation_strategy, "calls_used": 0, "gen_index": 0,
        "population": [], "run_trace_id": None, "gen_span_id": None, "auc_curve": [], "done": False,
    }


async def _run(sm, cfg, monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")

    from capychem import proposer as proposer_mod

    def distinct_valid(prompt, n, *, temperature, seed):
        return [proposer_mod.ProposalResult(raw="C" * (i + 2), smiles="C" * (i + 2),
                tokens_in=0, tokens_out=0, cost_usd=0.0) for i in range(n)]

    monkeypatch.setattr(proposer_mod, "_stub_propose", distinct_valid)

    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0)
            for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    async with sm() as s:
        run_id = await create_run(s, cfg)
    g = graph_mod.build_graph(sm)
    final = await g.ainvoke(_initial(run_id, cfg), config={"recursion_limit": 60})
    return run_id, final


async def test_analyze_persists_and_links_for_llm(sm, monkeypatch) -> None:
    cfg = RunConfig(task="qed", budget=200, seed=42, pop_size=6, offspring=4,
                    mutation_rate=0.01, plateau_window=9, max_generations=3,
                    mutation_strategy="llm")
    run_id, final = await _run(sm, cfg, monkeypatch)
    async with sm() as s:
        hyps = (await s.execute(select(AnalyzerHypothesis))).scalars().all()
        gens = (await s.execute(select(Generation).order_by(Generation.index))).scalars().all()
    # gen 0 (seed) has no hypothesis; gens >=1 each persist one, linked.
    assert len(hyps) >= 1
    assert all(h.after_generation_index >= 1 for h in hyps)
    gen0 = next(g for g in gens if g.index == 0)
    assert gen0.analyzer_hypothesis_id is None
    linked = [g for g in gens if g.index >= 1 and g.analyzer_hypothesis_id is not None]
    assert linked  # at least one gen>=1 linked its hypothesis
    # the threaded hypothesis is on the final state and feeds the next propose
    assert final.get("analyzer_hypothesis") is not None


async def test_graph_ga_run_does_not_analyze(sm, monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")

    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0)
            for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)

    def fake_offspring(population, n, *, mutation_rate, seed, **kw):
        from capychem.oracle import Offspring
        return [Offspring(smiles="C" * (i + 3), parents=(0, 0)) for i in range(n)]

    monkeypatch.setattr(graph_mod.strategy, "propose_offspring", fake_offspring)
    cfg = RunConfig(task="qed", budget=200, seed=42, pop_size=6, offspring=4,
                    mutation_rate=0.01, plateau_window=9, max_generations=3,
                    mutation_strategy="graph_ga")
    async with sm() as s:
        run_id = await create_run(s, cfg)
    g = graph_mod.build_graph(sm)
    await g.ainvoke(_initial(run_id, cfg), config={"recursion_limit": 60})
    async with sm() as s:
        hyps = (await s.execute(select(AnalyzerHypothesis))).scalars().all()
    assert hyps == []  # graph_ga is analyzer-free


async def test_analyze_fallback_on_malformed_keeps_running(sm, monkeypatch) -> None:
    # Force the analyzer to return no structured signal -> node uses neutral/last-good,
    # the loop still completes and persists a "no new signal" hypothesis.
    async def no_signal(summary, *, seed):
        return AnalyzerResult(text="unsure", structured=None, tokens_in=1, tokens_out=1,
                              cost_usd=0.0, note="no new signal")

    monkeypatch.setattr(graph_mod.strategy, "run_analyzer_async", no_signal)
    cfg = RunConfig(task="qed", budget=200, seed=42, pop_size=6, offspring=4,
                    mutation_rate=0.01, plateau_window=9, max_generations=3,
                    mutation_strategy="llm")
    run_id, final = await _run(sm, cfg, monkeypatch)
    assert final["done"] is True
    async with sm() as s:
        hyps = (await s.execute(select(AnalyzerHypothesis))).scalars().all()
    assert hyps and all(h.structured_json is None for h in hyps)


async def test_analyze_accumulates_surface_record_list(sm, monkeypatch) -> None:
    """Each LLM gen>=1 appends a {after_generation_index, text, structured_json}
    record to state['analyzer_hypotheses'], in order, mirroring the persisted rows."""
    cfg = RunConfig(task="qed", budget=200, seed=42, pop_size=6, offspring=4,
                    mutation_rate=0.01, plateau_window=9, max_generations=3,
                    mutation_strategy="llm")
    run_id, final = await _run(sm, cfg, monkeypatch)
    recs = final.get("analyzer_hypotheses")
    assert recs and len(recs) >= 1
    assert all(r["after_generation_index"] >= 1 for r in recs)
    assert all(isinstance(r["text"], str) and r["text"] for r in recs)
    idxs = [r["after_generation_index"] for r in recs]
    assert idxs == sorted(idxs)  # appended in generation order
    # the surface list mirrors the persisted AnalyzerHypothesis rows
    async with sm() as s:
        rows = (
            await s.execute(
                select(AnalyzerHypothesis).order_by(AnalyzerHypothesis.after_generation_index)
            )
        ).scalars().all()
    assert [r["after_generation_index"] for r in recs] == [
        row.after_generation_index for row in rows
    ]
    assert [r["text"] for r in recs] == [row.text for row in rows]


async def test_analyzer_cost_flows_into_llm_cost(sm, monkeypatch) -> None:
    async def costly(summary, *, seed):
        return AnalyzerResult(text='{"focus": "x", "avoid": []}',
                              structured={"focus": "x", "avoid": []},
                              tokens_in=0, tokens_out=0, cost_usd=0.01)

    monkeypatch.setattr(graph_mod.strategy, "run_analyzer_async", costly)
    cfg = RunConfig(task="qed", budget=200, seed=42, pop_size=6, offspring=4,
                    mutation_rate=0.01, plateau_window=9, max_generations=3,
                    mutation_strategy="llm")
    run_id, final = await _run(sm, cfg, monkeypatch)
    assert final.get("llm_cost_usd", 0.0) >= 0.01  # at least one analyzer call's cost summed in
