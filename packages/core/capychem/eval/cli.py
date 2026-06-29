"""``capychem-eval`` -- reproduce a PMO Graph-GA baseline and emit an AUC report.

Every reported score is an in-silico oracle score (PRD N6); the AUC is the
canonical PMO AUC-of-top-10 from eval/metric.py, not the live-UI running curve.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time

from capychem.eval.baselines import GRAPH_GA_AUC_TOP10, compare_to_baseline
from capychem.eval.metric import top_auc
from capychem.eval.runner import run_reproduction
from capychem.eval.trace import trace_to_dict


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="capychem-eval",
        description="Reproduce a PMO Graph-GA baseline (AUC top-10).",
    )
    p.add_argument("--task", default=None)
    p.add_argument(
        "--all",
        action="store_true",
        dest="all_tasks",
        help="Sweep all 23 PMO tasks; mode from --head-to-head/--analyzer-verdict (default reproduce).",  # noqa: E501
    )
    # --budget is BOTH the unique-call run-stop and the metric's max_oracle_calls.
    p.add_argument("--budget", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--pop-size", type=int, default=120)
    p.add_argument("--offspring", type=int, default=70)
    p.add_argument("--mutation-rate", type=float, default=0.067)
    p.add_argument("--mutation-strategy", choices=["graph_ga", "llm"], default="graph_ga")
    p.add_argument(
        "--head-to-head",
        action="store_true",
        help="Run llm vs graph_ga same-seed on --task and emit a beat verdict.",
    )
    p.add_argument(
        "--analyzer-verdict",
        action="store_true",
        help="Run llm with-analyzer vs without-analyzer same-seed on --task; emit the value verdict.",  # noqa: E501
    )
    p.add_argument(
        "--capture-analyzer-traces",
        action="store_true",
        help="Run the LLM-with-analyzer arm once and dump per-generation hypotheses + prompts (diagnosis).",  # noqa: E501
    )
    args = p.parse_args(argv)
    if not args.all_tasks and args.task is None:
        p.error("--task is required unless --all is given")

    t0 = time.monotonic()
    if args.all_tasks:
        from capychem.eval.sweep import run_sweep

        mode = (
            "analyzer_verdict" if args.analyzer_verdict
            else "head_to_head" if args.head_to_head
            else "reproduce"
        )
        sweep_report = run_sweep(
            budget=args.budget, seed=args.seed, mode=mode,
            pop_size=args.pop_size, offspring=args.offspring, mutation_rate=args.mutation_rate,
        )
        wall = time.monotonic() - t0
        sweep_out: dict[str, object] = {
            "sweep": True,
            **dataclasses.asdict(sweep_report),
            "wall_seconds": round(wall, 1),
        }
        json.dump(sweep_out, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.capture_analyzer_traces:
        from capychem.eval.trace import GenerationTrace

        sink: list[GenerationTrace] = []
        res = run_reproduction(
            args.task, args.budget, args.seed,
            pop_size=args.pop_size, offspring=args.offspring, mutation_rate=args.mutation_rate,
            mutation_strategy="llm", analyzer=True, trace_sink=sink,
        )
        wall = time.monotonic() - t0
        cap_report: dict[str, object] = {
            "task": args.task,
            "seed": args.seed,
            "budget": args.budget,
            "capture_analyzer_traces": True,
            "analyzer_calls": res.analyzer_calls,
            "analyzer_parsed": res.analyzer_parsed,
            "analyzer_parse_rate": res.analyzer_parse_rate,
            "traces": [trace_to_dict(t) for t in sink],
            "wall_seconds": round(wall, 1),
        }
        json.dump(cap_report, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.head_to_head:
        from capychem.eval.beat import run_head_to_head

        v = run_head_to_head(
            args.task,
            args.budget,
            args.seed,
            pop_size=args.pop_size,
            offspring=args.offspring,
            mutation_rate=args.mutation_rate,
        )
        wall = time.monotonic() - t0
        h2h_report: dict[str, object] = {
            "task": v.task,
            "seed": v.seed,
            "budget": v.budget,
            "head_to_head": True,
            "llm_auc": v.llm_auc,
            "graph_ga_auc": v.graph_ga_auc,
            "diff": v.diff,
            "beat": v.beat,
            "llm_valid_rate": v.llm_valid_rate,
            "llm_valid_gate": v.llm_valid_gate,
            "published_baseline": v.published_baseline,
            "llm_unique_calls": v.llm_unique_calls,
            "graph_ga_unique_calls": v.graph_ga_unique_calls,
            "wall_seconds": round(wall, 1),
        }
        json.dump(h2h_report, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.analyzer_verdict:
        from capychem.eval.verdict import run_analyzer_verdict

        av = run_analyzer_verdict(
            args.task,
            args.budget,
            args.seed,
            pop_size=args.pop_size,
            offspring=args.offspring,
            mutation_rate=args.mutation_rate,
        )
        wall = time.monotonic() - t0
        if not av.parse_rate_healthy:
            verdict_str = "INVALID — analyzer parse-rate <0.8; raise analyzer max_tokens and rerun"
        elif av.helps:
            verdict_str = "analyzer ADDS value (with_auc > without_auc)"
        else:
            verdict_str = (
                "analyzer NULL (with_auc <= without_auc) — "
                "pivot to analyzer-only narrative, do not abandon"
            )
        av_report: dict[str, object] = {
            "task": av.task,
            "seed": av.seed,
            "budget": av.budget,
            "analyzer_verdict": True,
            "with_auc": av.with_auc,
            "without_auc": av.without_auc,
            "diff": av.diff,
            "helps": av.helps,
            "analyzer_parse_rate": av.analyzer_parse_rate,
            "analyzer_calls": av.analyzer_calls,
            "analyzer_parsed": av.analyzer_parsed,
            "parse_rate_healthy": av.parse_rate_healthy,
            "with_valid_rate": av.with_valid_rate,
            "without_valid_rate": av.without_valid_rate,
            "with_unique_calls": av.with_unique_calls,
            "without_unique_calls": av.without_unique_calls,
            "verdict": verdict_str,
            "wall_seconds": round(wall, 1),
        }
        json.dump(av_report, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    res = run_reproduction(
        args.task,
        args.budget,
        args.seed,
        pop_size=args.pop_size,
        offspring=args.offspring,
        mutation_rate=args.mutation_rate,
        mutation_strategy=args.mutation_strategy,
    )
    auc = top_auc(res.mol_buffer, top_n=10, finish=True, freq_log=100, max_oracle_calls=args.budget)
    wall = time.monotonic() - t0

    report: dict[str, object] = {
        "task": args.task,
        "seed": args.seed,
        "budget": args.budget,
        "pop_size": args.pop_size,
        "offspring": args.offspring,
        "mutation_rate": args.mutation_rate,
        "unique_calls_used": res.unique_calls,
        "generations": res.generations,
        "auc_top10": auc,
        "wall_seconds": round(wall, 1),
    }
    if args.task in GRAPH_GA_AUC_TOP10:
        cmp = compare_to_baseline(args.task, auc)
        report |= {
            "baseline_published": cmp.baseline,
            "tolerance": cmp.tolerance,
            "diff": cmp.diff,
            "within_tolerance": cmp.within_tolerance,
        }
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
