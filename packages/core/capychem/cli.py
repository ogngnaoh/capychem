"""`capychem-run` — local end-to-end driver for the optimization loop.

Parses run config, creates a Run row, runs the LangGraph loop to budget/cap, and
prints a final summary. This is the slice's end-to-end proof.

Usage: capychem-run --task qed --budget 200 --seed 42 [--pop-size 100]
       [--offspring 32] [--mutation-rate 0.01] [--plateau-window 5]
       [--max-generations 100]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from capychem.db.models import Run
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.loop import trace
from capychem.loop.graph import build_graph
from capychem.loop.state import LoopState


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="capychem-run")
    p.add_argument("--task", default="qed")
    p.add_argument("--budget", type=int, required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--pop-size", type=int, default=100)
    p.add_argument("--offspring", type=int, default=32)
    p.add_argument("--mutation-rate", type=float, default=0.01)
    p.add_argument("--plateau-window", type=int, default=5)
    p.add_argument("--max-generations", type=int, default=100)
    args = p.parse_args(argv)
    if args.budget <= 0:
        p.error("--budget must be a positive integer")  # FR-015
    if args.pop_size <= 1:
        p.error("--pop-size must be > 1 (crossover needs two parents)")
    return args


async def run(args: argparse.Namespace) -> dict[str, Any]:
    engine = make_engine()
    await init_schema(engine)
    sessionmaker = make_sessionmaker(engine)

    async with sessionmaker() as session:
        run_row = Run(
            task=args.task,
            budget=args.budget,
            mutation_strategy="graph_ga",
            plateau_window=args.plateau_window,
            pop_size=args.pop_size,
            offspring=args.offspring,
            mutation_rate=args.mutation_rate,
            seed=args.seed,
            status="running",
        )
        session.add(run_row)
        await session.commit()
        run_id = run_row.id

    run_span_id = trace.trace_run(run_id, args.task)
    graph = build_graph(sessionmaker)

    initial: LoopState = {
        "run_id": run_id,
        "task": args.task,
        "budget": args.budget,
        "seed": args.seed,
        "pop_size": args.pop_size,
        "offspring": args.offspring,
        "mutation_rate": args.mutation_rate,
        "plateau_window": args.plateau_window,
        "max_generations": args.max_generations,
        "calls_used": 0,
        "gen_index": 0,
        "population": [],
        "run_span_id": run_span_id,
        "gen_span_id": run_span_id,
        "auc_curve": [],
        "done": False,
    }
    # Each generation is 5 node-steps; allow headroom over the cap.
    recursion_limit = args.max_generations * 6 + 10
    final: dict[str, Any] = await graph.ainvoke(
        initial, config={"recursion_limit": recursion_limit}
    )

    async with sessionmaker() as session:
        row = await session.get(Run, run_id)
        assert row is not None
        row.status = final.get("stop_reason") or "exhausted"
        row.summary_json = final.get("summary")
        await session.commit()

    trace.flush()
    await engine.dispose()
    summary = final.get("summary") or {}
    return {
        "run_id": run_id,
        "stop_reason": final.get("stop_reason"),
        "calls_used": final.get("calls_used"),
        # report completed-generation COUNT (summary's value = gen_index + 1), not the
        # last processed index, so the CLI print and summary_json agree.
        "generations": summary.get("generations"),
        "summary": final.get("summary"),
    }


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = asyncio.run(run(args))
    summary = result["summary"] or {}
    top = summary.get("top_k", [])[:10]
    print(f"\nRun {result['run_id']} — {result['stop_reason']}")
    print(f"  oracle calls used: {result['calls_used']}  generations: {result['generations']}")
    print("  top molecules:")
    for i, m in enumerate(top, 1):
        print(f"    {i:2d}. {m['score']:.4f}  {m['smiles']}")


if __name__ == "__main__":
    main()
