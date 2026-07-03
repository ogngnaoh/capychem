"""Reconstruct a paused run's LoopState progress fields from persisted DB rows.

Replays the SAME merge_and_truncate / top-10-mean / unique-call-buffer logic the
live persist node applies (packages/core/capychem/loop/graph.py ``_persist``),
generation by generation, so a resumed run reaches the same terminal state an
uninterrupted run would (G6). Pure DB reads -- no harness, no I/O beyond the
session.
"""

from __future__ import annotations

from typing import Any

from capychem.db.models import AnalyzerHypothesis, Candidate, Generation, Run, RunCost
from capychem.loop.logic import _sort_key, merge_and_truncate
from capychem.loop.state import Hypothesis, Scored
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _scored_from(candidate: Candidate) -> Scored:
    assert candidate.score is not None, "the persist node only writes scored candidates"
    return Scored(smiles=candidate.smiles, score=candidate.score, candidate_id=candidate.id)


async def reconstruct_state(session: AsyncSession, run_id: int) -> dict[str, Any]:
    """Replay a run's persisted Generations/Candidates into the progress fields
    that seed a resumed LoopState: gen_index, population, mol_buffer, calls_used,
    auc_curve, analyzer_hypothesis, llm_cost_usd."""
    run = await session.get(Run, run_id)
    assert run is not None, f"Run {run_id} not found"

    gen_indices = (
        await session.execute(
            select(Generation.index)
            .where(Generation.run_id == run_id)
            .order_by(Generation.index)
        )
    ).scalars().all()

    cand_rows = (
        await session.execute(
            select(Candidate, Generation.index)
            .join(Generation, Candidate.generation_id == Generation.id)
            .where(Generation.run_id == run_id)
            .order_by(Generation.index, Candidate.id)
        )
    ).all()
    by_index: dict[int, list[Candidate]] = {}
    for cand, idx in cand_rows:
        by_index.setdefault(idx, []).append(cand)

    population: list[Scored] = []
    buffer: set[str] = set()
    auc_curve: list[tuple[int, float]] = []
    for idx in gen_indices:
        gen_candidates = by_index.get(idx, [])
        gen_scored = [_scored_from(c) for c in gen_candidates]
        population = merge_and_truncate(population, gen_scored, pop_size=run.pop_size)
        buffer |= {c.smiles for c in gen_candidates}
        top10 = sorted(population, key=_sort_key)[:10]
        top10_mean = sum(m.score for m in top10) / len(top10) if top10 else 0.0
        auc_curve.append((len(buffer), top10_mean))

    hyp_row = await session.scalar(
        select(AnalyzerHypothesis)
        .where(AnalyzerHypothesis.run_id == run_id)
        .order_by(AnalyzerHypothesis.after_generation_index.desc(), AnalyzerHypothesis.id.desc())
        .limit(1)
    )
    hypothesis = (
        Hypothesis(structured=hyp_row.structured_json, text=hyp_row.text)
        if hyp_row is not None
        else None
    )

    cost_row = await session.scalar(select(RunCost).where(RunCost.run_id == run_id))
    llm_cost_usd = cost_row.llm_cost_usd if cost_row is not None else 0.0

    return {
        "gen_index": (gen_indices[-1] + 1) if gen_indices else 0,
        "population": population,
        "mol_buffer": buffer,
        "calls_used": len(buffer),
        "auc_curve": auc_curve,
        "analyzer_hypothesis": hypothesis,
        "llm_cost_usd": llm_cost_usd,
    }
