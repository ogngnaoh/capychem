"""Headless, memoized Graph-GA reproduction runner.

No Postgres, no LangGraph. Reuses the production oracle/validate/merge
primitives; the ONLY differences from the product loop are (a) a memoizing
mol_buffer keyed by canonical SMILES so budget counts UNIQUE oracle calls, and
(b) no persistence. Used by ``capychem-eval`` to reproduce PMO baselines (every
score is an in-silico oracle score, per PRD N6).
"""

from __future__ import annotations

from dataclasses import dataclass

from capychem.loop.logic import merge_and_truncate
from capychem.loop.seeds import load_starting_pop as starting_population  # pure file read
from capychem.loop.state import Scored
from capychem.oracle import propose_offspring, score_smiles
from capychem.validate import validate_batch


@dataclass(frozen=True)
class ReproResult:
    mol_buffer: dict[str, tuple[float, int]]
    generations: int
    unique_calls: int


def _as_scored(pairs: list[tuple[str, float]]) -> list[Scored]:
    return [Scored(smiles=s, score=sc) for s, sc in pairs]


def _top_k_mean(buf: dict[str, tuple[float, int]], k: int) -> float:
    scores = sorted((score for score, _ in buf.values()), reverse=True)[:k]
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
) -> ReproResult:
    mol_buffer: dict[str, tuple[float, int]] = {}

    def score_unique(smiles_list: list[str]) -> list[tuple[str, float]]:
        """Score only unseen SMILES; memoize; return (smiles, score) for all known."""
        unseen = [s for s in smiles_list if s not in mol_buffer]
        # respect the unique-call budget: only score up to remaining headroom
        room = budget - len(mol_buffer)
        if room > 0 and unseen:
            for r in score_smiles(unseen[:room], task):
                if r.valid and r.score is not None and r.smiles not in mol_buffer:
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

    # --- generations 1..N ---
    while len(mol_buffer) < budget:
        offs = propose_offspring(
            [(s.smiles, s.score) for s in population],
            offspring,
            mutation_rate=mutation_rate,
            seed=seed + generations,
        )
        valid = validate_batch([(o.smiles, o.parents) for o in offs])
        new_scored = score_unique([c.smiles for c in valid])
        population = merge_and_truncate(population, _as_scored(new_scored), pop_size=pop_size)
        generations += 1

        # PMO patience: top-100 mean improvement < 1e-3 -> decrement; break at 0
        cur_top = _top_k_mean(mol_buffer, 100)
        if cur_top - prev_top < 1e-3:
            patience_left -= 1
            if patience_left <= 0:
                break
        else:
            patience_left = patience
        prev_top = cur_top

    return ReproResult(
        mol_buffer=mol_buffer, generations=generations, unique_calls=len(mol_buffer)
    )
