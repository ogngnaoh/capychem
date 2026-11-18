"""With/without-analyzer value verdict: does the analyzer add AUC-of-top-10 value?

Both
arms run the headless ``run_reproduction`` with the LLM proposer at the SAME seed —
the only difference is the analyzer (off vs on), which first conditions the proposer
at generation 2. Both are measured with the canonical PMO ``top_auc`` (never ad hoc).
The with-arm's ``parse_hypothesis`` success rate guards the verdict: below
``_PARSE_RATE_FLOOR`` the reasoning-mode chain-of-thought is crowding out the
{focus, avoid} JSON, so a null is untrustworthy (raise analyzer max_tokens, rerun).
Every score is an in-silico oracle score.
"""

from __future__ import annotations

from dataclasses import dataclass

from capychem.eval.metric import top_auc
from capychem.eval.runner import run_reproduction

# Shared parsing threshold: below this the with-arm's hypotheses are not really parsing,
# so the AUC delta is not a true with/without comparison. In capychem.trust.gates.
from capychem.trust.gates import PARSE_RATE_FLOOR as _PARSE_RATE_FLOOR


@dataclass(frozen=True)
class AnalyzerVerdict:
    task: str
    seed: int
    budget: int
    with_auc: float
    without_auc: float
    diff: float  # with_auc - without_auc
    helps: bool  # with_auc > without_auc
    analyzer_parse_rate: float | None
    analyzer_calls: int
    analyzer_parsed: int
    parse_rate_healthy: bool
    with_valid_rate: float | None
    without_valid_rate: float | None
    with_unique_calls: int
    without_unique_calls: int


def run_analyzer_verdict(
    task: str,
    budget: int,
    seed: int,
    *,
    pop_size: int = 120,
    offspring: int = 70,
    mutation_rate: float = 0.067,
) -> AnalyzerVerdict:
    """Run llm-with-analyzer and llm-without-analyzer same-seed, measure both via
    ``top_auc``, return the verdict. The analyzer is the only treatment difference."""
    with_a = run_reproduction(
        task, budget, seed,
        pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
        mutation_strategy="llm", analyzer=True,
    )
    without_a = run_reproduction(
        task, budget, seed,
        pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
        mutation_strategy="llm", analyzer=False,
    )
    with_auc = top_auc(with_a.mol_buffer, top_n=10, max_oracle_calls=budget)
    without_auc = top_auc(without_a.mol_buffer, top_n=10, max_oracle_calls=budget)
    rate = with_a.analyzer_parse_rate
    return AnalyzerVerdict(
        task=task,
        seed=seed,
        budget=budget,
        with_auc=with_auc,
        without_auc=without_auc,
        diff=with_auc - without_auc,
        helps=with_auc > without_auc,
        analyzer_parse_rate=rate,
        analyzer_calls=with_a.analyzer_calls,
        analyzer_parsed=with_a.analyzer_parsed,
        parse_rate_healthy=(rate is not None and rate >= _PARSE_RATE_FLOOR),
        with_valid_rate=with_a.valid_rate,
        without_valid_rate=without_a.valid_rate,
        with_unique_calls=with_a.unique_calls,
        without_unique_calls=without_a.unique_calls,
    )
