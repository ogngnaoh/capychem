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


async def test_cost_cap_trips_on_llm_spend_alone(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Oracle cost is 0 (fake scorer); the LLM proposals carry a large cost, so the
    # gate must trip on total_usd = oracle + llm (slice 05).
    from capychem.loop import graph as graph_mod
    from capychem.loop import strategy
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    async def fake_llm(task, population, *, n, seed, hypothesis=None):
        return [
            ProposalResult(
                raw="C" * (i + 1), smiles="C" * (i + 1),
                tokens_in=1000, tokens_out=1000, cost_usd=100.0,
            )
            for i in range(n)
        ]

    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=0, cost_usd=0.0)
            for s in smiles
        ]

    monkeypatch.setattr(strategy, "propose_llm_async", fake_llm)
    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)

    registry = RunRegistry(sm)
    cfg = RunConfig(
        task="qed", budget=20, seed=42, pop_size=6, offspring=6,
        mutation_rate=0.01, plateau_window=3, max_generations=5,
        mutation_strategy="llm",
    )
    run_id = await registry.start_run(cfg)
    handle = registry._runs[run_id]
    await handle.task

    assert handle.terminal_event is not None
    assert handle.terminal_event["status"] == "cost_capped"
    async with sm() as session:
        run = await session.get(Run, run_id)
        rc = await session.scalar(select(RunCost).where(RunCost.run_id == run_id))
    assert run is not None and run.status == "cost_capped"
    assert rc is not None
    assert rc.oracle_cost_usd == pytest.approx(0.0)
    assert rc.llm_cost_usd >= 50.0                    # gen-1 LLM spend alone exceeds the $50 cap
    assert rc.total_usd == pytest.approx(rc.llm_cost_usd)


async def test_cost_cap_trips_on_analyzer_spend(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Cheap proposer + zero oracle, but the ANALYZER carries a large cost_usd, so the
    # gate must trip on total_usd including the analyzer term (milestone 03 slice 05).
    from capychem.analyzer import AnalyzerResult
    from capychem.loop import graph as graph_mod
    from capychem.loop import strategy
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    async def cheap_llm(task, population, *, n, seed, hypothesis=None):
        return [
            ProposalResult(
                raw="C" * (i + 1), smiles="C" * (i + 1),
                tokens_in=1, tokens_out=1, cost_usd=0.0,
            )
            for i in range(n)
        ]

    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=0, cost_usd=0.0)
            for s in smiles
        ]

    async def pricey_analyzer(summary, *, seed):
        return AnalyzerResult(
            text="focus on rings", structured={"focus": "rings", "avoid": []},
            tokens_in=1000, tokens_out=1000, cost_usd=100.0,
        )

    monkeypatch.setattr(strategy, "propose_llm_async", cheap_llm)
    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    monkeypatch.setattr(strategy, "run_analyzer_async", pricey_analyzer)

    registry = RunRegistry(sm)
    cfg = RunConfig(
        task="qed", budget=20, seed=42, pop_size=6, offspring=6,
        mutation_rate=0.01, plateau_window=3, max_generations=5,
        mutation_strategy="llm",
    )
    run_id = await registry.start_run(cfg)
    handle = registry._runs[run_id]
    await handle.task

    assert handle.terminal_event is not None
    assert handle.terminal_event["status"] == "cost_capped"
    async with sm() as session:
        run = await session.get(Run, run_id)
        rc = await session.scalar(select(RunCost).where(RunCost.run_id == run_id))
    assert run is not None and run.status == "cost_capped"
    assert rc is not None
    assert rc.oracle_cost_usd == pytest.approx(0.0)   # oracle is free here
    assert rc.llm_cost_usd >= 50.0                     # analyzer spend alone (proposer=0) caps it
    assert rc.total_usd == pytest.approx(rc.llm_cost_usd)
