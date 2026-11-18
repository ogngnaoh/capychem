"""Headless, memoized Graph-GA reproduction runner.

No Postgres, no LangGraph. Reuses the production oracle/validate/merge
primitives; the ONLY differences from the product loop are (a) a memoizing
mol_buffer keyed by canonical SMILES so budget counts UNIQUE oracle calls, and
(b) no persistence. Used by ``capychem-eval`` to reproduce PMO baselines (every
score is an in-silico oracle score).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from capychem.eval.trace import GenerationTrace
from capychem.loop.logic import build_analyzer_summary, merge_and_truncate
from capychem.loop.seeds import load_starting_pop as starting_population  # pure file read
from capychem.loop.state import Hypothesis, Scored
from capychem.loop.strategy import (
    build_prompt,
    fallback_fill,
    propose_llm_sync,
    resolve_effective_hypothesis,
    run_analyzer_sync,
)
from capychem.oracle import propose_offspring, score_smiles
from capychem.validate import validate_batch, validate_batch_with_stats


@dataclass(frozen=True)
class ReproResult:
    mol_buffer: dict[str, tuple[float, int]]
    generations: int
    unique_calls: int
    llm_proposed: int = 0
    llm_valid: int = 0
    valid_rate: float | None = None
    analyzer_calls: int = 0
    analyzer_parsed: int = 0
    analyzer_parse_rate: float | None = None


def _as_scored(pairs: list[tuple[str, float]]) -> list[Scored]:
    return [Scored(smiles=s, score=sc) for s, sc in pairs]


def _top_k_mean(buf: dict[str, tuple[float, int]], k: int) -> float:
    scores = sorted((score for score, _ in buf.values()), reverse=True)[:k]
    return sum(scores) / len(scores) if scores else 0.0


def _pop_top_k_mean(population: list[Scored], k: int) -> float:
    scores = sorted((m.score for m in population), reverse=True)[:k]
    return sum(scores) / len(scores) if scores else 0.0


def run_reproduction(
    task: str,
    budget: int,
    seed: int,
    *,
    pop_size: int = 120,
    offspring: int = 70,
    mutation_rate: float = 0.067,
    patience: int = 5,
    freq_log: int = 100,
    mutation_strategy: str = "graph_ga",
    analyzer: bool = False,
    trace_sink: list[GenerationTrace] | None = None,
) -> ReproResult:
    mol_buffer: dict[str, tuple[float, int]] = {}

    def score_unique(smiles_list: list[str]) -> list[tuple[str, float]]:
        """Score only unseen SMILES; memoize; return (smiles, score) for all known.

        Precondition: ``smiles_list`` is already canonicalized + intra-batch
        deduped by ``validate_batch`` upstream, so ``unseen[:room]`` cannot waste
        a headroom slot on an intra-batch duplicate.
        """
        unseen = [s for s in smiles_list if s not in mol_buffer]
        # respect the unique-call budget: only score up to remaining headroom
        room = budget - len(mol_buffer)
        if room > 0 and unseen:
            for r in score_smiles(unseen[:room], task):
                # A valid SMILES can still score NaN/±inf (e.g. sitagliptin_mpo). NaN is
                # not None, so it slips past the None gate and poisons the patience read
                # (`NaN - prev < 1e-3` is always False -> no early stop -> budget blowup)
                # and the AUC. Drop non-finite scores at ingestion.
                if (
                    r.valid
                    and r.score is not None
                    and math.isfinite(r.score)
                    and r.smiles not in mol_buffer
                ):
                    mol_buffer[r.smiles] = (r.score, len(mol_buffer) + 1)
        return [(s, mol_buffer[s][0]) for s in smiles_list if s in mol_buffer]

    # --- generation 0: seed population ---
    seeds = starting_population(pop_size)
    valid0 = validate_batch([(s, None) for s in seeds])
    population = merge_and_truncate(
        [], _as_scored(score_unique([c.smiles for c in valid0])), pop_size=pop_size
    )

    generations = 1
    patience_left = patience
    prev_top = _top_k_mean(mol_buffer, 100)
    llm_proposed = 0
    llm_valid = 0
    analyzer_calls = 0
    analyzer_parsed = 0
    hypothesis: Hypothesis | None = None
    # Match the product loop's auc_curve EXACTLY: top-10 mean of the SURVIVOR pool
    # (population), not the whole mol_buffer — so the analyzer's recent_top10_means are
    # byte-identical across paths even for small pop_size (G6). _top_k_mean(mol_buffer,…)
    # stays for the patience check (a separate quantity).
    score_history: list[float] = [_pop_top_k_mean(population, 10)]

    # --- generations 1..N ---
    while len(mol_buffer) < budget:
        pop_pairs = [(s.smiles, s.score) for s in population]
        if mutation_strategy == "llm":
            results = propose_llm_sync(
                task, pop_pairs, n=offspring, seed=seed + generations, hypothesis=hypothesis
            )
            valid_llm, stats = validate_batch_with_stats([(r.smiles, None) for r in results])
            llm_proposed += stats.proposed
            llm_valid += stats.valid
            fillers = fallback_fill(
                valid_llm,
                pop_pairs,
                target=offspring,
                mutation_rate=mutation_rate,
                seed=seed + generations,
            )
            valid = [*valid_llm, *fillers]
        else:
            offs = propose_offspring(
                pop_pairs,
                offspring,
                mutation_rate=mutation_rate,
                seed=seed + generations,
            )
            valid = validate_batch([(o.smiles, o.parents) for o in offs])
        new_scored = score_unique([c.smiles for c in valid])
        population = merge_and_truncate(population, _as_scored(new_scored), pop_size=pop_size)
        generations += 1

        score_history.append(_pop_top_k_mean(population, 10))
        if analyzer and mutation_strategy == "llm":
            summary = build_analyzer_summary(population, score_history, hypothesis)
            # `generations` was already incremented above, so generation N's analyzer
            # seed must be seed+N — matching the product node's seed+gen_index for the
            # generation just scored (G6 parity). Hence `generations - 1`.
            result = run_analyzer_sync(summary, seed=seed + generations - 1)
            analyzer_calls += 1
            if result.structured is not None:
                analyzer_parsed += 1
            if trace_sink is not None:
                trace_sink.append(GenerationTrace(
                    generation=generations,
                    summary_top=summary.top,
                    summary_bottom=summary.bottom,
                    recent_top10_means=summary.recent_top10_means,
                    prior_structured=hypothesis.structured if hypothesis else None,
                    analyzer_raw=result.text,
                    analyzer_structured=result.structured,
                    prompt_used=build_prompt(task, pop_pairs, offspring, hypothesis),
                    prompt_unconditioned=build_prompt(task, pop_pairs, offspring, None),
                ))
            hypothesis = resolve_effective_hypothesis(result, hypothesis)

        # PMO patience: top-100 mean improvement < 1e-3 -> decrement; break at 0
        cur_top = _top_k_mean(mol_buffer, 100)
        if cur_top - prev_top < 1e-3:
            patience_left -= 1
            if patience_left <= 0:
                break
        else:
            patience_left = patience
        prev_top = cur_top

    valid_rate = (llm_valid / llm_proposed) if llm_proposed else None
    analyzer_parse_rate = (analyzer_parsed / analyzer_calls) if analyzer_calls else None
    return ReproResult(
        mol_buffer=mol_buffer,
        generations=generations,
        unique_calls=len(mol_buffer),
        llm_proposed=llm_proposed,
        llm_valid=llm_valid,
        valid_rate=valid_rate,
        analyzer_calls=analyzer_calls,
        analyzer_parsed=analyzer_parsed,
        analyzer_parse_rate=analyzer_parse_rate,
    )
