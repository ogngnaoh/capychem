"""End-to-end test: capychem-run on the real harness QED oracle + Postgres.

Small pop + a budget covering gen 0 + >=2 offspring generations, so monotonicity
is non-vacuous. Asserts rows persist with provenance, budget is never exceeded,
best-score is monotonic non-decreasing, and same seed -> identical top-K (G6).
"""

from __future__ import annotations

import pytest
from capychem.cli import parse_args, run
from capychem.db.models import Candidate, Generation, OracleCall
from capychem.db.session import make_engine, make_sessionmaker
from sqlalchemy import func, select

# pop_size 20 (gen 0) + ~10 + ~10 ≈ 40 scored calls fits in 60 with headroom.
_ARGV = [
    "--task",
    "qed",
    "--budget",
    "60",
    "--seed",
    "42",
    "--pop-size",
    "20",
    "--offspring",
    "10",
    "--max-generations",
    "50",
]


@pytest.mark.asyncio
async def test_cli_run_persists_and_is_monotonic() -> None:
    result = await run(parse_args(_ARGV))
    run_id = result["run_id"]
    assert result["calls_used"] <= 60  # FR-002: never exceeds budget
    assert result["generations"] >= 2  # monotonicity is non-vacuous

    engine = make_engine()
    sessionmaker = make_sessionmaker(engine)
    async with sessionmaker() as session:
        gens = (
            (
                await session.execute(
                    select(Generation).where(Generation.run_id == run_id).order_by(Generation.index)
                )
            )
            .scalars()
            .all()
        )
        assert len(gens) >= 3  # gen 0 + >=2 offspring gens

        n_calls = (
            await session.execute(
                select(func.count()).select_from(OracleCall).where(OracleCall.run_id == run_id)
            )
        ).scalar_one()
        assert n_calls == result["calls_used"]

        # gen-0 candidates have no parent; gen->=1 candidates do.
        gen0_cands = (
            (await session.execute(select(Candidate).where(Candidate.generation_id == gens[0].id)))
            .scalars()
            .all()
        )
        assert gen0_cands and all(c.parent_candidate_id is None for c in gen0_cands)

        later_cands = (
            (await session.execute(select(Candidate).where(Candidate.generation_id == gens[-1].id)))
            .scalars()
            .all()
        )
        assert later_cands and any(c.parent_candidate_id is not None for c in later_cands)
    await engine.dispose()

    # best-score-so-far monotonic non-decreasing across the AUC curve
    curve = result["summary"]["auc_curve"]
    means = [pt["top10_mean"] for pt in curve]
    assert means == sorted(means), f"top-10 mean must be non-decreasing: {means}"


@pytest.mark.asyncio
async def test_cli_run_is_deterministic_for_same_seed() -> None:
    a = await run(parse_args(_ARGV))
    b = await run(parse_args(_ARGV))
    top_a = [(m["smiles"], round(m["score"], 6)) for m in a["summary"]["top_k"]]
    top_b = [(m["smiles"], round(m["score"], 6)) for m in b["summary"]["top_k"]]
    assert top_a == top_b
