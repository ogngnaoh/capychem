"""The loop persists a per-run valid_smiles block in summary_json.

Drives the real graph with a fake scorer (no harness). Graph-GA / starting-pop
SMILES are all RDKit-valid, so the measured rate is 1.0 — the deliverable is the
plumbing, not the number.
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


async def test_summary_has_valid_smiles_block(sm, monkeypatch):
    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0)
            for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    from capychem.run import RunConfig, create_run

    cfg = RunConfig(
        task="qed",
        budget=4,
        seed=42,
        pop_size=4,
        offspring=4,
        mutation_rate=0.01,
        plateau_window=2,
        max_generations=1,
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
    vs = final["summary"]["valid_smiles"]
    assert vs["proposed"] >= vs["valid"] > 0
    assert vs["rate"] == 1.0  # starting-pop SMILES are all valid
