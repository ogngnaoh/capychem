"""Mode-pluggable PMO sweep runner: walk a task list, run the existing per-task
primitive for the chosen mode, aggregate per-task rows + a summary.

This is pure orchestration — it adds NO new AUC or comparator logic (the canonical
PMO ``top_auc`` and the existing head-to-head / analyzer-verdict primitives do all the
measuring). One task throwing is isolated to its own row so a long sweep never aborts.
Every score is an in-silico oracle score (PRD N6).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from capychem.eval.baselines import GRAPH_GA_AUC_TOP10, compare_to_baseline
from capychem.eval.beat import run_head_to_head
from capychem.eval.metric import top_auc
from capychem.eval.runner import run_reproduction
from capychem.eval.tasks import PMO_TASKS
from capychem.eval.verdict import run_analyzer_verdict


@dataclass(frozen=True)
class SweepRow:
    task: str
    ok: bool
    headline_auc: float | None  # reproduce: auc_top10; h2h: llm_auc; verdict: with_auc
    beat: bool | None  # h2h: beat; verdict: helps; reproduce: None
    payload: dict[str, Any]  # the mode's per-task report fields, or {"error": ...}


@dataclass(frozen=True)
class SweepReport:
    mode: str
    budget: int
    seed: int
    tasks_run: int  # successful rows
    tasks_failed: int
    auc_sum: float  # sum of headline_auc over successful rows
    published_sum: float  # sum of published Graph-GA baselines over the input tasks
    beats: int | None  # count of beat/helps (None for reproduce)
    rows: list[SweepRow]


def _run_one(
    task: str,
    *,
    budget: int,
    seed: int,
    mode: str,
    pop_size: int,
    offspring: int,
    mutation_rate: float,
) -> SweepRow:
    if mode == "reproduce":
        res = run_reproduction(
            task, budget, seed,
            pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
            mutation_strategy="graph_ga",
        )
        auc = top_auc(
            res.mol_buffer, top_n=10, finish=True, freq_log=100, max_oracle_calls=budget
        )
        payload: dict[str, Any] = {
            "auc_top10": auc,
            "unique_calls_used": res.unique_calls,
            "generations": res.generations,
        }
        if task in GRAPH_GA_AUC_TOP10:
            cmp = compare_to_baseline(task, auc)
            payload |= {
                "baseline_published": cmp.baseline,
                "tolerance": cmp.tolerance,
                "diff": cmp.diff,
                "within_tolerance": cmp.within_tolerance,
            }
        return SweepRow(task=task, ok=True, headline_auc=auc, beat=None, payload=payload)

    if mode == "head_to_head":
        v = run_head_to_head(
            task, budget, seed,
            pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
        )
        return SweepRow(task=task, ok=True, headline_auc=v.llm_auc, beat=v.beat, payload=asdict(v))

    if mode == "analyzer_verdict":
        v2 = run_analyzer_verdict(
            task, budget, seed,
            pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
        )
        return SweepRow(
            task=task, ok=True, headline_auc=v2.with_auc, beat=v2.helps, payload=asdict(v2)
        )

    raise ValueError(
        f"Use a known sweep mode (reproduce|head_to_head|analyzer_verdict); got {mode!r}."
    )


def run_sweep(
    tasks: tuple[str, ...] = PMO_TASKS,
    *,
    budget: int,
    seed: int,
    mode: str = "reproduce",
    pop_size: int = 120,
    offspring: int = 70,
    mutation_rate: float = 0.067,
) -> SweepReport:
    if mode not in ("reproduce", "head_to_head", "analyzer_verdict"):
        raise ValueError(
            f"Use a known sweep mode (reproduce|head_to_head|analyzer_verdict); got {mode!r}."
        )
    rows: list[SweepRow] = []
    for task in tasks:
        try:
            rows.append(
                _run_one(
                    task, budget=budget, seed=seed, mode=mode,
                    pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
                )
            )
        except Exception as exc:  # per-task isolation: one failure never aborts the sweep
            rows.append(
                SweepRow(task=task, ok=False, headline_auc=None, beat=None,
                         payload={"error": str(exc)})
            )
    ok_rows = [r for r in rows if r.ok]
    auc_sum = sum((r.headline_auc for r in ok_rows if r.headline_auc is not None), 0.0)
    published_sum = sum((GRAPH_GA_AUC_TOP10[t] for t in tasks if t in GRAPH_GA_AUC_TOP10), 0.0)
    beats = None if mode == "reproduce" else sum(1 for r in ok_rows if r.beat)
    return SweepReport(
        mode=mode, budget=budget, seed=seed,
        tasks_run=len(ok_rows), tasks_failed=len(rows) - len(ok_rows),
        auc_sum=auc_sum, published_sum=published_sum, beats=beats, rows=rows,
    )
