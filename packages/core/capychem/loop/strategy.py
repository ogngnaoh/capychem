"""Shared proposer strategy pieces for milestone-02 slice 04, extended in milestone-03.

Both the product loop (``loop/graph.py``) and the headless eval runner
(``eval/runner.py``) import these so the LLM path is byte-identical in each — G6
reproducibility. ``build_prompt`` is the MOLLEO-style mutation prompt, optionally
conditioned on the analyzer hypothesis (milestone 03). ``ga_fill`` wraps the Graph-GA
seam for BOTH the ``graph_ga`` strategy and the LLM fallback; ``fallback_fill`` is
the invalid-output backfill (FR-005). Temperature is pinned (G6).
"""

from __future__ import annotations

import asyncio

from capychem.analyzer import AnalyzerResult, analyze_async, analyze_sync
from capychem.loop.state import AnalyzerSummary, Hypothesis
from capychem.oracle import propose_offspring
from capychem.proposer import ProposalResult, propose_batch_async
from capychem.validate import ValidCandidate, validate_batch

LLM_TEMPERATURE = 0.7
# Fraction of each generation's offspring conditioned on the analyzer hypothesis;
# the remainder use the plain prompt to preserve batch diversity (milestone 03 redesign).
CONDITIONED_FRACTION = 0.5


def build_prompt(
    task: str,
    population: list[tuple[str, float]],
    n: int,
    hypothesis: Hypothesis | None = None,
) -> str:
    """MOLLEO-style single-molecule mutation prompt, optionally conditioned on the
    analyzer hypothesis. With no structured hypothesis the output is byte-identical
    to the unconditioned milestone-02 prompt (gen-1 / graph_ga regression)."""
    top = sorted(population, key=lambda p: (-p[1], p[0]))[:10]
    lines = "\n".join(f"{smi}\t{score:.4f}" for smi, score in top)
    guidance = ""
    if hypothesis is not None and hypothesis.structured is not None:
        s = hypothesis.structured
        guidance = (
            "\nAn analysis of the previous generation suggests this MAY help — treat it as "
            "optional inspiration, not a constraint, and prioritize your own chemical judgment: "
            f"consider {s['focus']}. {hypothesis.text}\n"
        )
    return (
        f"You are optimizing molecules for the '{task}' objective (higher score is better).\n"
        f"Current best molecules (SMILES, score):\n{lines}\n"
        f"{guidance}\n"
        "Propose ONE new, valid, drug-like molecule likely to score higher. "
        "Output only its SMILES string — no prose, no code fences."
    )


async def propose_llm_async(
    task: str,
    population: list[tuple[str, float]],
    *,
    n: int,
    seed: int,
    hypothesis: Hypothesis | None = None,
    conditioned_fraction: float = CONDITIONED_FRACTION,
) -> list[ProposalResult]:
    """Propose ``n`` LLM candidates (pinned temperature + per-gen seed, G6). When a
    structured hypothesis is present and ``conditioned_fraction`` < 1.0, only that
    fraction of the batch is conditioned; the rest use the plain prompt to preserve
    diversity. No structured hypothesis (or fraction >= 1.0) -> single plain batch,
    byte-identical to milestone 02."""
    if hypothesis is None or hypothesis.structured is None or conditioned_fraction >= 1.0:
        return await propose_batch_async(
            build_prompt(task, population, n, hypothesis), n,
            temperature=LLM_TEMPERATURE, seed=seed,
        )
    n_cond = round(n * conditioned_fraction)
    n_plain = n - n_cond
    out: list[ProposalResult] = []
    if n_cond:
        out += await propose_batch_async(
            build_prompt(task, population, n_cond, hypothesis), n_cond,
            temperature=LLM_TEMPERATURE, seed=seed,
        )
    if n_plain:
        out += await propose_batch_async(
            build_prompt(task, population, n_plain, None), n_plain,
            temperature=LLM_TEMPERATURE, seed=seed + n_cond,
        )
    return out


def propose_llm_sync(
    task: str,
    population: list[tuple[str, float]],
    *,
    n: int,
    seed: int,
    hypothesis: Hypothesis | None = None,
    conditioned_fraction: float = CONDITIONED_FRACTION,
) -> list[ProposalResult]:
    """Synchronous bridge for the headless eval path (no running event loop)."""
    return asyncio.run(propose_llm_async(
        task, population, n=n, seed=seed, hypothesis=hypothesis,
        conditioned_fraction=conditioned_fraction,
    ))


def build_analyzer_prompt(summary: AnalyzerSummary) -> str:
    """Template the generation summary into the analyzer instruction. Asks for
    prose followed by a JSON {"focus","avoid"} object so parse_hypothesis can lift it."""
    top = "\n".join(f"{smi}\t{score:.4f}" for smi, score in summary.top)
    bottom = "\n".join(f"{smi}\t{score:.4f}" for smi, score in summary.bottom)
    deltas = ", ".join(f"{d:.4f}" for d in summary.recent_top10_means)
    prior = ""
    if summary.prior is not None and summary.prior.structured is not None:
        ps = summary.prior.structured
        prior = f"Prior hypothesis: focus={ps['focus']}; avoid={ps['avoid']}.\n"
    return (
        "You are analyzing one generation of a molecular optimization loop.\n"
        f"Top molecules (SMILES, score):\n{top}\n\n"
        f"Bottom molecules (SMILES, score):\n{bottom}\n\n"
        f"Recent top-10 mean trajectory: {deltas}\n"
        f"{prior}\n"
        "Reason about which structural features are improving the score, then output a short "
        "prose explanation followed by a JSON object on its own line of the form "
        '{"focus": "<one concrete thing to pursue>", "avoid": ["<thing to steer away from>"]}.'
    )


async def run_analyzer_async(summary: AnalyzerSummary, *, seed: int) -> AnalyzerResult:
    """Build the analyzer prompt + call the adapter (async product-loop path)."""
    return await analyze_async(build_analyzer_prompt(summary), seed=seed)


def run_analyzer_sync(summary: AnalyzerSummary, *, seed: int) -> AnalyzerResult:
    """Build the analyzer prompt + call the adapter (sync headless path)."""
    return analyze_sync(build_analyzer_prompt(summary), seed=seed)


def resolve_effective_hypothesis(
    result: AnalyzerResult, prior: Hypothesis | None
) -> Hypothesis:
    """The effective hypothesis the loop threads forward: the freshly parsed one,
    else the last-good (flagged 'no new signal'), else a neutral hypothesis. Shared
    by the product node (graph.py) and the headless runner (eval/runner.py) so both
    paths resolve identically (G6). The loop never stalls on malformed/empty output
    (FR-007, edge case 3)."""
    if result.structured is not None:
        return Hypothesis(structured=result.structured, text=result.text)
    if prior is not None:
        return Hypothesis(structured=prior.structured, text=prior.text, note="no new signal")
    return Hypothesis(
        structured=None,
        text="No new signal; continue broad optimization.",
        note="no new signal",
    )


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
