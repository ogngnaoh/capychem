"""06-07 Part 1: reconstruct_state replays persisted Generations/Candidates into
the exact progress fields the live persist node would have produced, so a
resumed LoopState is G6-exact."""

from __future__ import annotations

import pytest
from capychem.db.models import AnalyzerHypothesis, Base, Candidate, Generation, RunCost
from capychem.loop.state import Hypothesis, Scored
from capychem.resume import reconstruct_state
from capychem.run import RunConfig, create_run
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_reconstruct_matches_live_state(sm) -> None:  # type: ignore[no-untyped-def]
    cfg = RunConfig(
        task="qed", budget=100, seed=42, pop_size=2, offspring=3,
        mutation_rate=0.01, plateau_window=5, max_generations=10,
        mutation_strategy="llm",
    )
    async with sm() as s:
        run_id = await create_run(s, cfg)

        # Generation 0: A(0.5) B(0.3) C(0.7) -- merge_and_truncate(pop_size=2) keeps
        # the top 2 by (-score, smiles): C(0.7), A(0.5).
        gen0 = Generation(run_id=run_id, index=0, proposer_used="starting")
        s.add(gen0)
        await s.flush()
        cand_a = Candidate(
            generation_id=gen0.id, smiles="A", proposer="starting", valid=True, score=0.5
        )
        cand_b = Candidate(
            generation_id=gen0.id, smiles="B", proposer="starting", valid=True, score=0.3
        )
        cand_c = Candidate(
            generation_id=gen0.id, smiles="C", proposer="starting", valid=True, score=0.7
        )
        s.add_all([cand_a, cand_b, cand_c])
        await s.flush()

        # Generation 1: D(0.9) E(0.1) -- merged with [C, A] -> top2 = D(0.9), C(0.7).
        gen1 = Generation(run_id=run_id, index=1, proposer_used="llm")
        s.add(gen1)
        await s.flush()
        cand_d = Candidate(generation_id=gen1.id, smiles="D", proposer="llm", valid=True, score=0.9)
        cand_e = Candidate(generation_id=gen1.id, smiles="E", proposer="llm", valid=True, score=0.1)
        s.add_all([cand_d, cand_e])
        await s.flush()

        # Generation 2: F(0.95) alone -- merged with [D, C] -> top2 = F(0.95), D(0.9).
        gen2 = Generation(run_id=run_id, index=2, proposer_used="llm")
        s.add(gen2)
        await s.flush()
        cand_f = Candidate(
            generation_id=gen2.id, smiles="F", proposer="llm", valid=True, score=0.95
        )
        s.add(cand_f)
        await s.flush()

        s.add_all([
            AnalyzerHypothesis(
                run_id=run_id, after_generation_index=1, text="first",
                structured_json={"focus": "rings", "avoid": []},
            ),
            AnalyzerHypothesis(
                run_id=run_id, after_generation_index=2, text="second",
                structured_json={"focus": "amides", "avoid": ["esters"]},
            ),
        ])
        s.add(RunCost(run_id=run_id, llm_cost_usd=12.34, oracle_cost_usd=0.0, total_usd=12.34))
        await s.commit()

        out = await reconstruct_state(s, run_id)

    assert out["gen_index"] == 3  # max(Generation.index) + 1 == 2 + 1
    assert out["mol_buffer"] == {"A", "B", "C", "D", "E", "F"}
    assert out["calls_used"] == 6

    pop = out["population"]
    assert [(m.smiles, m.score) for m in pop] == [("F", 0.95), ("D", 0.9)]
    assert all(isinstance(m, Scored) for m in pop)
    assert {m.candidate_id for m in pop} == {cand_f.id, cand_d.id}

    assert out["auc_curve"] == [
        (3, (0.7 + 0.5) / 2),   # gen 0: buffer={A,B,C}, top10=[C,A]
        (5, (0.9 + 0.7) / 2),   # gen 1: buffer +={D,E}, top10=[D,C]
        (6, (0.95 + 0.9) / 2),  # gen 2: buffer +={F}, top10=[F,D]
    ]

    hyp = out["analyzer_hypothesis"]
    assert isinstance(hyp, Hypothesis)
    assert hyp.text == "second"  # the LAST (highest after_generation_index) row
    assert hyp.structured == {"focus": "amides", "avoid": ["esters"]}

    assert out["llm_cost_usd"] == pytest.approx(12.34)


async def test_reconstruct_no_generations_returns_zeroed_progress(sm) -> None:  # type: ignore[no-untyped-def]
    cfg = RunConfig(
        task="qed", budget=100, seed=42, pop_size=4, offspring=4,
        mutation_rate=0.01, plateau_window=5, max_generations=10,
    )
    async with sm() as s:
        run_id = await create_run(s, cfg)
        out = await reconstruct_state(s, run_id)

    assert out == {
        "gen_index": 0,
        "population": [],
        "mol_buffer": set(),
        "calls_used": 0,
        "auc_curve": [],
        "analyzer_hypothesis": None,
        "llm_cost_usd": 0.0,
    }
