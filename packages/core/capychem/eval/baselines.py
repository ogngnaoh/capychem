"""Published PMO Graph-GA AUC-top-10 baselines (NeurIPS 2022 Table 2) and the
reproduction tolerance. Source: agent_docs/pmo-auc-and-baselines.md."""

from __future__ import annotations

from dataclasses import dataclass

# Published Graph-GA AUC top-10, mean over 5 seeds (PMO paper Table 2). Sum = 13.751.
# These are a single-vs-5-seed SANITY REFERENCE only: every head-to-head / verdict
# decision uses our own same-seed Graph-GA control, never the published number as the
# comparator. Source: agent_docs/pmo-auc-and-baselines.md.
GRAPH_GA_AUC_TOP10: dict[str, float] = {
    "qed": 0.940,
    "zaleplon_mpo": 0.346,
    "perindopril_mpo": 0.538,
    "celecoxib_rediscovery": 0.630,
    "troglitazone_rediscovery": 0.390,
    "drd2": 0.964,
    "jnk3": 0.553,
    "gsk3b": 0.788,
    "albuterol_similarity": 0.838,
    "amlodipine_mpo": 0.661,
    "deco_hop": 0.619,
    "fexofenadine_mpo": 0.760,
    "isomers_c7h8n2o2": 0.862,
    "isomers_c9h10n2o2pf2cl": 0.719,
    "median1": 0.294,
    "median2": 0.273,
    "mestranol_similarity": 0.579,
    "osimertinib_mpo": 0.831,
    "ranolazine_mpo": 0.728,
    "scaffold_hop": 0.517,
    "sitagliptin_mpo": 0.433,
    "thiothixene_rediscovery": 0.479,
    "valsartan_smarts": 0.000,
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
