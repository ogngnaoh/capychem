"""In-process background runner: drives the slice-2 loop via astream.

One asyncio task per run. The task consumes ``graph.astream(stream_mode="values")``,
updates a per-run snapshot, broadcasts generation.complete / run.complete to
subscribed asyncio.Queues, and stops at a generation boundary when the run's
cancel Event is set. The loop code itself is never modified — we only observe it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, cast

from capychem.api.schemas import GenerationCompleteEvent, RunCompleteEvent, TopMolecule
from capychem.loop import trace
from capychem.loop.graph import build_graph
from capychem.loop.logic import build_summary
from capychem.loop.state import LoopState
from capychem.run import RunConfig, create_run, finalize_run
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


def _snapshot_from_state(run_id: int, cfg: RunConfig, state: dict[str, Any]) -> dict[str, Any]:
    pop = state.get("population", [])
    top = sorted(pop, key=lambda m: (-m.score, m.smiles))[:10]
    curve = state.get("auc_curve", [])
    return {
        "run_id": run_id,
        "task": cfg.task,
        "status": "running",
        "budget": cfg.budget,
        # completed-generation COUNT (== summary["generations"]); len(curve) grows
        # by one per persisted generation, whereas state["gen_index"] lags by one at
        # the moment the curve grows. Using len(curve) keeps the live UI and the
        # final summary_json["generations"] in agreement.
        "generation_index": len(curve),
        "oracle_calls_used": state.get("calls_used", 0),
        "best_score": (top[0].score if top else None),
        "top_k": [{"smiles": m.smiles, "score": m.score} for m in top],
        "auc_curve": [{"oracle_calls": c, "top10_mean": v} for c, v in curve],
    }


@dataclass
class RunHandle:
    run_id: int
    config: RunConfig
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    snapshot: dict[str, Any] | None = None
    task: asyncio.Task[None] | None = None
    # The run.complete event dict, set just before broadcast. Lets a subscriber
    # that connects after completion get the terminal event replayed (handles
    # are never evicted).
    terminal_event: dict[str, Any] | None = None

    def broadcast(self, event: dict[str, Any]) -> None:
        for q in list(self.subscribers):
            q.put_nowait(event)


class RunRegistry:
    """Owns the live runs. Single-process, single event loop (MVP)."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker
        self._runs: dict[int, RunHandle] = {}

    async def start_run(self, config: RunConfig) -> int:
        async with self._sm() as session:
            run_id = await create_run(session, config)
        handle = RunHandle(run_id=run_id, config=config)
        self._runs[run_id] = handle
        handle.task = asyncio.create_task(self._drive(handle))
        return run_id

    def subscribe(self, run_id: int) -> asyncio.Queue[dict[str, Any]]:
        """Subscribe to a run's event stream.

        Contract:
        - An unknown ``run_id`` returns an orphan queue that never yields.
        - The queue itself does no replay: a subscriber joining after completion
          gets nothing from it — callers must check ``terminal_event`` /
          ``snapshot`` first (the WS endpoint does).
        - Callers must ``unsubscribe`` in a ``finally`` block.
        """
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        handle = self._runs.get(run_id)
        if handle is not None:
            handle.subscribers.add(q)
        return q

    def unsubscribe(self, run_id: int, q: asyncio.Queue[dict[str, Any]]) -> None:
        handle = self._runs.get(run_id)
        if handle is not None:
            handle.subscribers.discard(q)

    def snapshot(self, run_id: int) -> dict[str, Any] | None:
        handle = self._runs.get(run_id)
        return handle.snapshot if handle is not None else None

    def is_live(self, run_id: int) -> bool:
        return run_id in self._runs

    async def stop_run(self, run_id: int) -> bool:
        handle = self._runs.get(run_id)
        if handle is None:
            return False
        if handle.terminal_event is not None or (handle.task is not None and handle.task.done()):
            return False  # already finished — nothing to stop
        handle.cancel.set()
        return True

    async def shutdown(self) -> None:
        """Cancel all outstanding driver tasks (called from the app lifespan
        BEFORE engine.dispose(), so disposal never races an in-flight _drive)."""
        tasks = [h.task for h in self._runs.values() if h.task is not None and not h.task.done()]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _drive(self, handle: RunHandle) -> None:
        cfg = handle.config
        run_span_id = trace.trace_run(handle.run_id, cfg.task)  # None when Langfuse is off
        graph = build_graph(self._sm)
        initial: LoopState = {
            "run_id": handle.run_id,
            "task": cfg.task,
            "budget": cfg.budget,
            "seed": cfg.seed,
            "pop_size": cfg.pop_size,
            "offspring": cfg.offspring,
            "mutation_rate": cfg.mutation_rate,
            "plateau_window": cfg.plateau_window,
            "max_generations": cfg.max_generations,
            "calls_used": 0,
            "gen_index": 0,
            "population": [],
            "run_span_id": run_span_id,
            "gen_span_id": run_span_id,
            "auc_curve": [],
            "done": False,
        }
        # Each generation is 5 node-steps; allow headroom over the cap (mirrors cli.py).
        recursion_limit = cfg.max_generations * 6 + 10
        last_curve_len = 0
        final_state: dict[str, Any] = {}
        stopped = False
        # astream is an async generator at runtime; its declared AsyncIterator type
        # lacks aclose(), so cast for the explicit close in the finally block.
        stream = cast(
            AsyncGenerator[dict[str, Any], None],
            graph.astream(
                initial, config={"recursion_limit": recursion_limit}, stream_mode="values"
            ),
        )
        errored = False
        try:
            async for state in stream:
                final_state = state
                if len(state.get("auc_curve", [])) > last_curve_len:
                    last_curve_len = len(state["auc_curve"])
                    handle.snapshot = _snapshot_from_state(handle.run_id, cfg, state)
                    snap = handle.snapshot
                    handle.broadcast(
                        GenerationCompleteEvent(
                            generation_index=snap["generation_index"],
                            # The population is non-empty at a generation boundary
                            # (the curve only grows after a scored generation), so
                            # best_score is always set here.
                            best_score=snap["best_score"],
                            oracle_calls_used=snap["oracle_calls_used"],
                            top_k=[TopMolecule(**m) for m in snap["top_k"]],
                        ).model_dump()
                    )
                    if handle.cancel.is_set():
                        stopped = True
                        break
        except Exception:
            # NOT asyncio.CancelledError — that derives from BaseException in 3.12,
            # so shutdown cancellation propagates past this handler. Keep it that way.
            errored = True
            logger.exception("run %d errored mid-loop", handle.run_id)
        finally:
            await stream.aclose()

        if errored:
            status = "errored"
            summary = None
        else:
            status = "stopped" if stopped else (final_state.get("stop_reason") or "exhausted")
            summary = final_state.get("summary")
            if summary is None and final_state:
                # The cooperative-stop break happens after persist but BEFORE stop_check
                # populates state["summary"], so build it here from the final state.
                # This makes the stopped run's partial state durable in summary_json
                # (design §8 exit criterion), not just live in the in-memory handle.
                summary = build_summary(
                    final_state.get("population", []),
                    final_state.get("auc_curve", []),
                    generations=last_curve_len,
                    oracle_calls=final_state.get("calls_used", 0),
                )
        async with self._sm() as session:
            await finalize_run(session, handle.run_id, {"stop_reason": status, "summary": summary})
        trace.flush()
        if handle.snapshot is not None:
            handle.snapshot["status"] = status  # terminal status for a post-completion GET
        terminal = RunCompleteEvent(
            run_id=handle.run_id, status=status, summary=summary
        ).model_dump()
        handle.terminal_event = terminal  # replay source for late WS subscribers
        handle.broadcast(terminal)
        # The handle stays in the registry (never evicted) so a post-completion GET/WS
        # reads the terminal in-memory snapshot. Acceptable for single-user MVP.
