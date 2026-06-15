"""Published PMO Graph-GA AUC-top-10 baselines (NeurIPS 2022 Table 2) and the
reproduction tolerance. Source: agent_docs/pmo-auc-and-baselines.md."""

from __future__ import annotations

from dataclasses import dataclass

# Published Graph-GA AUC top-10, mean over 5 seeds (PMO paper Table 2).
GRAPH_GA_AUC_TOP10: dict[str, float] = {
    "qed": 0.940,
    # Add other tasks when reproduced (milestone 02+). QED is the smoke target.
}

# Reproduction tolerance (our engineering recommendation, not a PMO-published
# value): absorbs starting-pop + single-vs-5-seed variance; tight enough to
# catch a broken metric/pipeline.
DEFAULT_TOLERANCE = 0.02


@dataclass(frozen=True)
class BaselineComparison:
    task: str
    auc: float
    baseline: float
    tolerance: float
    diff: float  # auc - baseline
    within_tolerance: bool


def compare_to_baseline(
    task: str, auc: float, tolerance: float = DEFAULT_TOLERANCE
) -> BaselineComparison:
    if task not in GRAPH_GA_AUC_TOP10:
        raise KeyError(
            f"No published Graph-GA baseline for task {task!r}; add it to GRAPH_GA_AUC_TOP10."
        )
    baseline = GRAPH_GA_AUC_TOP10[task]
    diff = auc - baseline
    return BaselineComparison(task, auc, baseline, tolerance, diff, abs(diff) <= tolerance)
