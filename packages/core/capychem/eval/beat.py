"""Head-to-head beat verdict: LLM proposer vs our own same-seed Graph-GA control.

Both runs go through the headless
``run_reproduction`` (deterministic, no DB) and are measured with the canonical
PMO ``top_auc`` — never an ad-hoc AUC. Every score is an in-silico oracle score.
The published baseline (if any) is a sanity reference, not the comparator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from capychem.eval.baselines import GRAPH_GA_AUC_TOP10
from capychem.eval.metric import top_auc
from capychem.eval.runner import run_reproduction
from capychem.loop.logic import valid_smiles_gate

# Shared parsing threshold: below this the with-analyzer arm's hypotheses are not really
# parsing (a $0-balance mid-run degrades the LLM arm to Graph-GA), so a beat is not
# trustworthy. De-duplicated into capychem.trust.gates.
from capychem.trust.gates import PARSE_RATE_FLOOR as _PARSE_RATE_FLOOR


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
    # with-analyzer-arm health (milestone 03 slice 05); defaults keep the
    # existing analyzer-off head_to_head constructions unchanged.
    analyzer: bool = False
    analyzer_parse_rate: float | None = None
    analyzer_calls: int = 0
    analyzer_parsed: int = 0
    parse_rate_healthy: bool = False


def run_head_to_head(
    task: str,
    budget: int,
    seed: int,
    *,
    pop_size: int = 120,
    offspring: int = 70,
    mutation_rate: float = 0.067,
    analyzer: bool = False,
) -> BeatVerdict:
    """Run graph_ga and llm same-seed, measure both via top_auc, return the verdict.

    ``analyzer=True`` runs the LLM arm WITH the analyzer (the Week-8 bar:
    with-analyzer-LLM vs vanilla Graph-GA). ``parse_rate_healthy`` then guards the
    beat alongside ``llm_valid_gate``.
    """
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
        analyzer=analyzer,
    )
    ga_auc = top_auc(ga.mol_buffer, top_n=10, max_oracle_calls=budget)
    llm_auc = top_auc(llm.mol_buffer, top_n=10, max_oracle_calls=budget)
    rate = llm.valid_rate
    gate = valid_smiles_gate(rate) if rate is not None else None
    parse_rate = llm.analyzer_parse_rate
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
        analyzer=analyzer,
        analyzer_parse_rate=parse_rate,
        analyzer_calls=llm.analyzer_calls,
        analyzer_parsed=llm.analyzer_parsed,
        parse_rate_healthy=(
            analyzer and parse_rate is not None and parse_rate >= _PARSE_RATE_FLOOR
        ),
    )
