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

    if mode == "week8":
        v3 = run_head_to_head(
            task, budget, seed,
            pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
            analyzer=True,
        )
        return SweepRow(task=task, ok=True, headline_auc=v3.llm_auc, beat=v3.beat, payload=asdict(v3))

    raise ValueError(
        "Use a known sweep mode (reproduce|head_to_head|analyzer_verdict|week8); "
        f"got {mode!r}."
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
    if mode not in ("reproduce", "head_to_head", "analyzer_verdict", "week8"):
        raise ValueError(
            "Use a known sweep mode (reproduce|head_to_head|analyzer_verdict|week8); "
            f"got {mode!r}."
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


def week8_verdict(report: SweepReport) -> dict[str, Any]:
    """Guarded Week-8 read over a ``week8`` SweepReport.

    A beat counts only if BOTH the with-analyzer arm's valid-SMILES gate passed AND
    the analyzer parse-rate is healthy — a $0-balance mid-run silently degrades the
    LLM arm to Graph-GA (the slice-02 failure mode), which the guards catch. On a
    SUBSET, <3 trustworthy beats is INCONCLUSIVE, not "<3/23" -> not a clean pivot.
    """
    trustworthy = 0
    degraded: list[str] = []
    for r in report.rows:
        if not r.ok:
            continue
        gate = r.payload.get("llm_valid_gate")
        guards_ok = bool(gate and gate.get("passed")) and bool(
            r.payload.get("parse_rate_healthy")
        )
        if not guards_ok:
            degraded.append(r.task)
            continue
        if r.payload.get("beat"):
            trustworthy += 1
    on_track = trustworthy >= 3
    if on_track:
        verdict = (
            f"Week-8 bar CLEARED: {trustworthy} trustworthy beats (>=3 of the 23 PMO "
            "tasks) -> on track."
        )
    else:
        verdict = (
            f"INCONCLUSIVE: {trustworthy} trustworthy beats of {report.tasks_run} tasks "
            "run (<3). On a subset this cannot conclude <3/23 -> NOT a clean pivot; "
            "resolve with more budget."
        )
    return {
        "trustworthy_beats": trustworthy,
        "raw_beats": report.beats,
        "on_track": on_track,
        "degraded_tasks": degraded,
        "week8_verdict": verdict,
    }
