"""``capychem-eval`` -- reproduce a PMO Graph-GA baseline and emit an AUC report.

Every reported score is an in-silico oracle score (PRD N6); the AUC is the
canonical PMO AUC-of-top-10 from eval/metric.py, not the live-UI running curve.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from capychem.eval.baselines import GRAPH_GA_AUC_TOP10, compare_to_baseline
from capychem.eval.metric import top_auc
from capychem.eval.runner import run_reproduction


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="capychem-eval",
        description="Reproduce a PMO Graph-GA baseline (AUC top-10).",
    )
    p.add_argument("--task", required=True)
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
    args = p.parse_args(argv)

    t0 = time.monotonic()
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
