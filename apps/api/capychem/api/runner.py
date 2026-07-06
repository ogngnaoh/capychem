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

from capychem import cost
from capychem.api.schemas import (
    AnalyzerHypothesisEvent,
    GenerationCompleteEvent,
    RunCompleteEvent,
    TopMolecule,
)
from capychem.db.models import Run
from capychem.loop import trace
from capychem.loop.graph import build_graph
from capychem.loop.logic import build_summary, stop_reason
from capychem.loop.state import LoopState
from capychem.oracle import HarnessError
from capychem.resume import reconstruct_state
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
        "mode": cfg.mode,  # carried so the live snapshot gates graph_ga_baseline (07-01)
        "status": "running",
        "budget": cfg.budget,
        "plateau_window": cfg.plateau_window,
        # completed-generation COUNT (== summary["generations"]); len(curve) grows
        # by one per persisted generation, whereas state["gen_index"] lags by one at
        # the moment the curve grows. Using len(curve) keeps the live UI and the
        # final summary_json["generations"] in agreement.
        "generation_index": len(curve),
        "oracle_calls_used": state.get("calls_used", 0),
        "best_score": (top[0].score if top else None),
        "top_k": [{"smiles": m.smiles, "score": m.score} for m in top],
        "auc_curve": [{"oracle_calls": c, "top10_mean": v} for c, v in curve],
        "cost_so_far_usd": 0.0,
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
        # run_ids with a resume in flight — guards the check-then-flip against a
        # concurrent double-resume (added synchronously before any await).
        self._resuming: set[int] = set()

    async def start_run(self, config: RunConfig) -> int:
        async with self._sm() as session:
            run_id = await create_run(session, config)
        handle = RunHandle(run_id=run_id, config=config)
        self._runs[run_id] = handle
        handle.task = asyncio.create_task(self._drive(handle))
        return run_id

    async def resume_run(self, run_id: int) -> str:
        """Continue a paused run (06-07) from its persisted progress — the SAME
        run_id, no new Run row. Reconstructs the LoopState progress fields via
        reconstruct_state (mirrors exactly how the live persist node built them),
        flips the row back to "running", then drives it: a reconstructed
        gen_index > 0 takes the graph's propose-from-population branch, so the
        gen-0 special case is bypassed automatically."""
        # Guard against a concurrent double-resume (double-click / client retry):
        # a live task for this run, or another resume already in flight. Both checks
        # + the add() run synchronously here, before the first await, so a second
        # concurrent call sees the reservation and is refused rather than spawning a
        # second _drive that would write duplicate Generation.index rows.
        live = self._runs.get(run_id)
        live_task_running = live is not None and live.task is not None and not live.task.done()
        if run_id in self._resuming or live_task_running:
            raise ValueError(f"Run {run_id} is already running or resuming")
        self._resuming.add(run_id)
        try:
            async with self._sm() as session:
                row = await session.get(Run, run_id)
                if row is None or row.status != "paused":
                    raise ValueError(f"Run {run_id} is not resumable")
                progress = await reconstruct_state(session, run_id)
                cfg = RunConfig(
                    task=row.task,
                    budget=row.budget,
                    seed=row.seed,
                    pop_size=row.pop_size,
                    offspring=row.offspring,
                    mutation_rate=row.mutation_rate,
                    plateau_window=row.plateau_window,
                    max_generations=row.max_generations,
                    mutation_strategy=row.mutation_strategy,
                    mode=row.mode,  # a resumed run keeps its mode (baseline gate stays correct)
                    seed_smiles=row.seed_smiles,  # provenance only; gen-0 is bypassed on resume
                    seed_source=row.seed_source,
                )
                # Already-terminal guard: a run swept to "paused" after a crash in
                # the window between its last generation's persist and finalize may
                # have ALREADY satisfied a stop condition. Finalize it with that
                # reason instead of driving a spurious extra generation past
                # max_generations / budget / plateau (G6). made_progress=True
                # suppresses the per-generation no_progress signal, which cannot be
                # evaluated from persisted rows.
                terminal_reason = stop_reason(
                    calls_used=progress["calls_used"],
                    budget=cfg.budget,
                    gen_index=progress["gen_index"],
                    max_generations=cfg.max_generations,
                    made_progress=True,
                    top10_history=[v for _, v in progress["auc_curve"]],
                    plateau_window=cfg.plateau_window,
                )
                if terminal_reason is not None:
                    summary = build_summary(
                        progress["population"],
                        progress["auc_curve"],
                        generations=len(progress["auc_curve"]),
                        oracle_calls=progress["calls_used"],
                    )
                    await finalize_run(
                        session, run_id, {"stop_reason": terminal_reason, "summary": summary}
                    )
                else:
                    row.status = "running"
                    await session.commit()
            if terminal_reason is not None:
                # Finalized above without driving. Register a handle carrying the
                # terminal event so the client's post-resume WS subscribe replays
                # run.complete; a GET reads the finalized DB row (snapshot stays None).
                handle = RunHandle(run_id=run_id, config=cfg)
                handle.terminal_event = RunCompleteEvent(
                    run_id=run_id, status=terminal_reason, summary=summary
                ).model_dump()
                self._runs[run_id] = handle
                handle.broadcast(handle.terminal_event)
                return terminal_reason
            handle = RunHandle(run_id=run_id, config=cfg)
            self._runs[run_id] = handle
            handle.task = asyncio.create_task(self._drive(handle, progress=progress))
            return "running"
        finally:
            # Registered above: subsequent resumes now hit the live-task check.
            self._resuming.discard(run_id)

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

    def terminal_event(self, run_id: int) -> dict[str, Any] | None:
        """The stored run.complete event for a finished run, else None."""
        handle = self._runs.get(run_id)
        return handle.terminal_event if handle is not None else None

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

    async def _drive(self, handle: RunHandle, progress: dict[str, Any] | None = None) -> None:
        cfg = handle.config
        run_trace_id = trace.trace_run(handle.run_id, cfg.task)  # None when Langfuse is off
        graph = build_graph(self._sm)
        # A resume (06-07) seeds the PROGRESS fields from reconstruct_state instead
        # of the fresh-run zeros; a resumed gen_index > 0 takes the graph's
        # propose-from-population branch, bypassing the gen-0 special case.
        prog = progress or {
            "calls_used": 0,
            "gen_index": 0,
            "population": [],
            "mol_buffer": set(),
            "auc_curve": [],
            "analyzer_hypothesis": None,
            "llm_cost_usd": 0.0,
        }
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
            "mutation_strategy": cfg.mutation_strategy,
            # Operator bring-your-own compounds (07-02): used only at a fresh run's
            # gen 0. On a resume, gen_index > 0 bypasses the gen-0 branch, so this is
            # inert there (cfg.seed_smiles is carried for provenance only).
            "seed_smiles": cfg.seed_smiles,
            "calls_used": prog["calls_used"],
            "gen_index": prog["gen_index"],
            "population": prog["population"],
            "mol_buffer": prog["mol_buffer"],
            "run_trace_id": run_trace_id,
            "gen_span_id": None,
            "auc_curve": prog["auc_curve"],
            "analyzer_hypothesis": prog["analyzer_hypothesis"],
            "llm_cost_usd": prog["llm_cost_usd"],
            "done": False,
        }
        # Each generation is 7 node-steps (analyze added in milestone 03); allow headroom.
        recursion_limit = cfg.max_generations * 7 + 10
        # A resumed run's curve already has entries -- only NEW ones (from
        # generations completed THIS drive) should broadcast.
        last_curve_len = len(initial["auc_curve"])
        last_hyp_len = 0
        # Seeded with the reconstructed progress on a resume (not on a fresh run,
        # where {} preserves the existing zero-generation-fault behavior below):
        # if the resumed drive re-faults before yielding even one new state, the
        # summary fallback below still reflects the reconstructed population
        # instead of erasing it (PRD edge case 2 — a paused run's partial results
        # stay durable/browseable; a re-pause must not regress that guarantee).
        final_state: dict[str, Any] = dict(prog) if progress is not None else {}
        stopped = False
        cost_capped = False
        # astream is an async generator at runtime; its declared AsyncIterator type
        # lacks aclose(), so cast for the explicit close in the finally block.
        stream = cast(
            AsyncGenerator[dict[str, Any], None],
            graph.astream(
                initial, config={"recursion_limit": recursion_limit}, stream_mode="values"
            ),
        )
        errored = False
        paused = False
        try:
            async for state in stream:
                final_state = state
                hyps = state.get("analyzer_hypotheses", [])
                if len(hyps) > last_hyp_len:
                    for rec in hyps[last_hyp_len:]:
                        handle.broadcast(
                            AnalyzerHypothesisEvent(
                                after_generation_index=rec["after_generation_index"],
                                text=rec["text"],
                                structured_json=rec["structured_json"],
                            ).model_dump()
                        )
                    last_hyp_len = len(hyps)
                if len(state.get("auc_curve", [])) > last_curve_len:
                    last_curve_len = len(state["auc_curve"])
                    handle.snapshot = _snapshot_from_state(handle.run_id, cfg, state)
                    snap = handle.snapshot
                    # Aggregate the run's oracle cost from persisted OracleCalls and
                    # the cumulative LLM proposer cost from loop state; upsert RunCost
                    # so total_usd = oracle + llm (record_oracle_cost commits internally).
                    async with self._sm() as session:
                        oracle = await cost.oracle_cost_so_far(session, handle.run_id)
                        llm = state.get("llm_cost_usd", 0.0)
                        row = await cost.record_oracle_cost(
                            session, handle.run_id, oracle, llm_usd=llm
                        )
                        total = row.total_usd
                    snap["cost_so_far_usd"] = total
                    handle.broadcast(
                        GenerationCompleteEvent(
                            generation_index=snap["generation_index"],
                            # The population is non-empty at a generation boundary
                            # (the curve only grows after a scored generation), so
                            # best_score is always set here.
                            best_score=snap["best_score"],
                            # Backend-authoritative top-10 mean: same value the REST
                            # snapshot returns, not the top-1 best_score.
                            top10_mean=snap["auc_curve"][-1]["top10_mean"],
                            oracle_calls_used=snap["oracle_calls_used"],
                            cost_so_far_usd=total,
                            top_k=[TopMolecule(**m) for m in snap["top_k"]],
                        ).model_dump()
                    )
                    if total >= cost.cost_cap_usd():
                        cost_capped = True
                        break
                    if handle.cancel.is_set():
                        stopped = True
                        break
        except HarnessError:
            # A sustained harness-subprocess fault: the loop already retried
            # transient blips on BOTH harness paths — scoring and Graph-GA
            # offspring/fallback (packages/core/capychem/loop/graph.py
            # _with_harness_retry) — so reaching here means the outage persisted
            # past that retry budget. Pause the run in a recoverable state rather
            # than losing work (PRD edge case 2), instead of falling through to the
            # generic errored path below. Placed BEFORE the broad `except
            # Exception` since HarnessError is a RuntimeError subclass.
            paused = True
            logger.warning("run %d paused by oracle fault", handle.run_id)
        except Exception:
            # NOT asyncio.CancelledError — that derives from BaseException in 3.12,
            # so shutdown cancellation propagates past this handler. Keep it that way.
            errored = True
            logger.exception("run %d errored mid-loop", handle.run_id)
        finally:
            await stream.aclose()
            # Guarantee no generation span is left open before flush(): a node error
            # or a cost-cap / cooperative-stop break exits BEFORE that generation's
            # stop_check, which is the only happy-path caller of end_gen_span.
            trace.end_all_gen_spans(handle.run_id)

        if paused:
            status = "paused"
            summary = final_state.get("summary")
            if summary is None and final_state:
                # The fault interrupts a generation before its stop_check populates
                # state["summary"], so build it here from the final state to keep
                # the paused run's partial results durable/browseable (mirrors the
                # cost_capped/stopped fallback below).
                summary = build_summary(
                    final_state.get("population", []),
                    final_state.get("auc_curve", []),
                    generations=last_curve_len,
                    oracle_calls=final_state.get("calls_used", 0),
                )
        elif errored:
            status = "errored"
            summary = None
        elif cost_capped:
            status = "cost_capped"
            summary = final_state.get("summary")
            if summary is None and final_state:
                # The cost-cap break happens after persist but before stop_check
                # populates state["summary"], so build it here from the final state
                # to keep the capped run's partial state durable (mirrors the
                # cooperative-stop path below).
                summary = build_summary(
                    final_state.get("population", []),
                    final_state.get("auc_curve", []),
                    generations=last_curve_len,
                    oracle_calls=final_state.get("calls_used", 0),
                )
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
        # Persist the run's Langfuse trace id in summary_json so the run-detail
        # view can deep-link to it (FR-014). No schema change — summary_json is an
        # existing JSON column. None when Langfuse is off or the run errored.
        if summary is not None and run_trace_id is not None:
            summary = {**summary, "trace_id": run_trace_id}
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
