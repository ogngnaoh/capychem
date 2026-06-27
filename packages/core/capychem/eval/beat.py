"""Head-to-head beat verdict: LLM proposer vs our own same-seed Graph-GA control.

The slice-06 / milestone-02 week-7 kill-switch. Both runs go through the headless
``run_reproduction`` (deterministic, no DB) and are measured with the canonical
PMO ``top_auc`` — never an ad-hoc AUC. Every score is an in-silico oracle score
(PRD N6). The published baseline (if any) is a sanity reference, not the comparator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from capychem.eval.baselines import GRAPH_GA_AUC_TOP10
from capychem.eval.metric import top_auc
from capychem.eval.runner import run_reproduction
from capychem.loop.logic import valid_smiles_gate


@dataclass(frozen=True)
class BeatVerdict:
    task: str
    seed: int
    budget: int
    llm_auc: float
    graph_ga_auc: float
    diff: float  # llm_auc - graph_ga_auc
    beat: bool  # llm_auc > graph_ga_auc
    llm_valid_rate: float | None
    llm_valid_gate: dict[str, Any] | None
    published_baseline: float | None  # sanity reference, if registered
    llm_unique_calls: int
    graph_ga_unique_calls: int


def run_head_to_head(
    task: str,
    budget: int,
    seed: int,
    *,
    pop_size: int = 120,
    offspring: int = 70,
    mutation_rate: float = 0.067,
) -> BeatVerdict:
    """Run graph_ga and llm same-seed, measure both via top_auc, return the verdict."""
    ga = run_reproduction(
        task,
        budget,
        seed,
        pop_size=pop_size,
        offspring=offspring,
        mutation_rate=mutation_rate,
        mutation_strategy="graph_ga",
    )
    llm = run_reproduction(
        task,
        budget,
        seed,
        pop_size=pop_size,
        offspring=offspring,
        mutation_rate=mutation_rate,
        mutation_strategy="llm",
    )
    ga_auc = top_auc(ga.mol_buffer, top_n=10, max_oracle_calls=budget)
    llm_auc = top_auc(llm.mol_buffer, top_n=10, max_oracle_calls=budget)
    rate = llm.valid_rate
    gate = valid_smiles_gate(rate) if rate is not None else None
    return BeatVerdict(
        task=task,
        seed=seed,
        budget=budget,
        llm_auc=llm_auc,
        graph_ga_auc=ga_auc,
        diff=llm_auc - ga_auc,
        beat=llm_auc > ga_auc,
        llm_valid_rate=rate,
        llm_valid_gate=gate,
        published_baseline=GRAPH_GA_AUC_TOP10.get(task),
        llm_unique_calls=llm.unique_calls,
        graph_ga_unique_calls=ga.unique_calls,
    )
