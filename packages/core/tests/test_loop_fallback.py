"""The fallback node backfills invalid LLM output with Graph-GA (slice 04, FR-005)."""

from __future__ import annotations

from typing import Any

import pytest
from capychem.db.models import Base, Candidate, Generation
from capychem.loop import graph as graph_mod
from capychem.loop.state import Scored
from capychem.validate import ValidCandidate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _state(proposer: str, validated: list[ValidCandidate]) -> dict[str, Any]:
    return {
        "_proposer": proposer,
        "validated": validated,
        "offspring": 4,
        "mutation_rate": 0.01,
        "seed": 42,
        "gen_index": 1,
        "population": [Scored(smiles="CCO", score=0.9), Scored(smiles="CCN", score=0.4)],
        "run_trace_id": None,
        "gen_span_id": None,
    }


async def test_fallback_backfills_gap_for_llm(monkeypatch) -> None:
    # 1 valid LLM candidate, offspring target 4 -> fill 3 from GA.
    monkeypatch.setattr(
        graph_mod.strategy, "fallback_fill",
        lambda validated, pop, *, target, mutation_rate, seed: [
            ValidCandidate(smiles=s, parents=(0, 1), proposer="graph_ga")
            for s in ("CCC", "CCCC", "CCCCC")
        ],
    )
    out = await graph_mod.fallback(_state("llm", [ValidCandidate("CCO", None, "llm")]))  # type: ignore[arg-type]
    assert len(out["_fallback_validated"]) == 3
    assert out["_proposer"] == "mixed"


async def test_fallback_is_noop_for_graph_ga() -> None:
    out = await graph_mod.fallback(_state("graph_ga", [ValidCandidate("CCC", (0, 1))]))  # type: ignore[arg-type]
    assert out == {}


async def test_fallback_is_noop_when_llm_batch_full(monkeypatch) -> None:
    full = [ValidCandidate(f"C{'C' * i}", None, "llm") for i in range(4)]
    out = await graph_mod.fallback(_state("llm", full))  # type: ignore[arg-type]
    assert out == {}


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_persist_records_per_candidate_proposer(sm) -> None:
    from capychem.db.models import Run

    async with sm() as s:
        run = Run(
            task="qed", budget=10, mutation_strategy="llm", plateau_window=2,
            pop_size=4, offspring=4, mutation_rate=0.01, seed=42, status="running",
        )
        s.add(run)
        await s.commit()
        run_id = run.id
    state: dict[str, Any] = {
        "run_id": run_id,
        "gen_index": 1,
        "_proposer": "mixed",
        "_scored": [
            (ValidCandidate("CCO", None, "llm"), 0.8, 0.0),
            (ValidCandidate("CCC", (0, 1), "graph_ga"), 0.6, 0.0),
        ],
        "population": [],
        "pop_size": 4,
        "task": "qed",
        "calls_used": 2,
        "auc_curve": [],
        "run_trace_id": None,
        "gen_span_id": None,
    }
    await graph_mod._persist(state, sm)  # type: ignore[arg-type]
    async with sm() as s:
        gen = (await s.execute(select(Generation))).scalars().one()
        cands = (await s.execute(select(Candidate).order_by(Candidate.smiles))).scalars().all()
    assert gen.proposer_used == "mixed"
    assert {c.proposer for c in cands} == {"llm", "graph_ga"}
