"""Shared proposer strategy pieces for milestone-02 slice 04.

Both the product loop (``loop/graph.py``) and the headless eval runner
(``eval/runner.py``) import these so the LLM path is byte-identical in each — G6
reproducibility. ``build_prompt`` is the MOLLEO-style mutation prompt (no analyzer
hypothesis yet — that arrives in milestone 03). ``ga_fill`` wraps the Graph-GA
seam for BOTH the ``graph_ga`` strategy and the LLM fallback; ``fallback_fill`` is
the invalid-output backfill (FR-005). Temperature is pinned (G6).
"""

from __future__ import annotations

import asyncio

from capychem.oracle import propose_offspring
from capychem.proposer import ProposalResult, propose_batch_async
from capychem.validate import ValidCandidate, validate_batch

LLM_TEMPERATURE = 0.7


def build_prompt(task: str, population: list[tuple[str, float]], n: int) -> str:
    """MOLLEO-style single-molecule mutation prompt.

    Lists the current best molecules (by score, descending) and asks for ONE new
    valid SMILES. The ``direct`` backend fans out ``n`` single-choice requests and
    ``_clean_smiles`` takes the first token, so one SMILES per completion.
    """
    top = sorted(population, key=lambda p: (-p[1], p[0]))[:10]
    lines = "\n".join(f"{smi}\t{score:.4f}" for smi, score in top)
    return (
        f"You are optimizing molecules for the '{task}' objective (higher score is better).\n"
        f"Current best molecules (SMILES, score):\n{lines}\n\n"
        "Propose ONE new, valid, drug-like molecule likely to score higher. "
        "Output only its SMILES string — no prose, no code fences."
    )


async def propose_llm_async(
    task: str, population: list[tuple[str, float]], *, n: int, seed: int
) -> list[ProposalResult]:
    """Propose ``n`` LLM candidates with a pinned temperature + per-gen seed (G6)."""
    return await propose_batch_async(
        build_prompt(task, population, n), n, temperature=LLM_TEMPERATURE, seed=seed
    )


def propose_llm_sync(
    task: str, population: list[tuple[str, float]], *, n: int, seed: int
) -> list[ProposalResult]:
    """Synchronous bridge for the headless eval path (no running event loop)."""
    return asyncio.run(propose_llm_async(task, population, n=n, seed=seed))


def ga_fill(
    population: list[tuple[str, float]], n: int, *, mutation_rate: float, seed: int
) -> list[tuple[str, tuple[int, int] | None]]:
    """Graph-GA offspring as (smiles, parents) pairs. Serves the graph_ga strategy
    AND the LLM fallback. May return fewer than ``n`` (crossover validity)."""
    offs = propose_offspring(population, n, mutation_rate=mutation_rate, seed=seed)
    return [(o.smiles, o.parents) for o in offs]


def fallback_fill(
    validated: list[ValidCandidate],
    population: list[tuple[str, float]],
    *,
    target: int,
    mutation_rate: float,
    seed: int,
) -> list[ValidCandidate]:
    """Backfill invalid LLM output with Graph-GA offspring so a generation reaches
    ``target`` valid candidates (FR-005). Single GA-fill round (no retry). Fillers
    are RDKit-validated and deduped against the LLM-valid set; tagged "graph_ga"."""
    gap = target - len(validated)
    if gap <= 0 or not population:
        return []
    fillers_raw = ga_fill(population, gap, mutation_rate=mutation_rate, seed=seed)
    existing = {v.smiles for v in validated}
    return [vc for vc in validate_batch(fillers_raw) if vc.smiles not in existing]
