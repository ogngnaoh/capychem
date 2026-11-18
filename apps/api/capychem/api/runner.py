"""In-process background runner: drives the slice-2 loop via astream.

One asyncio task per run. The task consumes ``graph.astream(stream_mode="values")``,
updates a per-run snapshot, broadcasts generation.complete / run.complete to
subscribed asyncio.Queues, and stops at a generation boundary when the run's
cancel Event is set. The loop code itself is never modified — we only observe it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from capychem import cost, proposer
from capychem.api import config
from capychem.api.events import EventKind, notify_run_event
from capychem.api.schemas import (
    AnalyzerHypothesisEvent,
    GenerationCompleteEvent,
    RunCompleteEvent,
    TopMolecule,
)
from capychem.db.models import Generation, Run
from capychem.db.queue import claim_next_run, release_run, renew_lease
from capychem.loop import trace
from capychem.loop.graph import build_graph
from capychem.loop.logic import build_summary, stop_reason
from capychem.loop.state import LoopState
from capychem.oracle import HarnessError, pytdc_version
from capychem.resume import reconstruct_state
from capychem.run import RunConfig, build_manifest, create_run, finalize_run
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# Durable-queue lease duration (milestone 08 slice 02): how long a claimed run's
# lease is held before it's considered abandoned. Overridable so a standalone
# apps/runner deployment can tune it independently of this default. A lease is
# renewed at 1/3 of this interval, giving 2 missed heartbeats of slack before
# another worker can reclaim a still-live run.
LEASE_TTL_S = int(os.environ.get("CAPYCHEM_LEASE_TTL_S", "60"))
_LEASE_RENEW_INTERVAL_S = LEASE_TTL_S / 3

# Backpressure (milestone 08 slice 05): the max number of runs THIS worker
# process (an apps/runner instance, or the API's inline dev/test worker --
# both are a RunRegistry) drives concurrently. Chosen over a 429 at POST
# /runs: the queue already models "not yet started" as a durable "queued" row,
# so a full worker simply refuses to claim more -- the row stays queued and is
# picked up by this worker once a slot frees, or by another worker/replica.
# POST /runs always returns "queued" either way; the cap is invisible to the
# producer. A plain constant (not re-read per call), matching LEASE_TTL_S.
MAX_CONCURRENT_RUNS = int(os.environ.get("CAPYCHEM_MAX_CONCURRENT_RUNS", "4"))


def _git_sha() -> str | None:
    """Best-effort current commit SHA for the manifest (07-06). None if not a git
    checkout or git is unavailable — provenance degrades gracefully."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


async def _notify_best_effort(
    session: AsyncSession, run_id: int, kind: EventKind, index: int | None = None
) -> None:
    """pg_notify a just-persisted event, tolerating failure (m08-03).

    LISTEN/NOTIFY delivery is inherently best-effort — the DB row a receiver
    re-reads is always the source of truth, and a dropped notify is recovered
    by the WS's DB-snapshot catch-up on the next connect/reconnect (see
    ws_runs.py) — so a notify failure must never abort the drive. This also
    keeps fast SQLite-backed unit tests (test_runner.py's fake-graph tests,
    which never touch Postgres) working: ``pg_notify`` doesn't exist on
    SQLite, and the notify there simply no-ops instead of erroring the run.
    """
    try:
        await notify_run_event(session, run_id, kind, index)
    except Exception:
        logger.warning("run %d: failed to notify %s (non-fatal)", run_id, kind, exc_info=True)


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
        # Populated from the summary at finalize (07-08); null while live.
        "diversity": None,
        "novelty": None,
    }


def _local_lease_fields(worker_id: str, lease_ttl_s: int) -> dict[str, Any]:
    """lease_owner/lease_expires_at/heartbeat_at computed from THIS process's
    wall clock, for the single-process self-claim paths (start_run,
    resume_run) — as opposed to capychem.db.queue's DB-clock (func.now())
    arithmetic, which is what the real multi-worker claim/renew/release
    protocol needs to stay skew-proof across hosts.

    A single process claiming, renewing, and releasing its OWN run never
    contends with another host's clock, so the simpler application-clock
    value is safe here — and, unlike a SQL-side ``func.now() + interval``
    expression, it round-trips correctly through SQLite too (some tests drive
    RunRegistry against an in-memory sqlite DB with a stubbed graph; SQLite
    has no native interval arithmetic, so a server-side expression stores a
    non-datetime value there). Naive UTC, matching every other datetime
    column on Run (started_at/ended_at), which are also naive.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    return {
        "lease_owner": worker_id,
        "lease_expires_at": now + timedelta(seconds=lease_ttl_s),
        "heartbeat_at": now,
    }


def _config_from_row(row: Run) -> RunConfig:
    """Reconstruct a RunConfig from a persisted Run row -- the shape a claimed
    run needs when this process didn't already know it via a pending handle
    (a crash-reclaim of a DIFFERENT worker's run, or a manual /resume)."""
    return RunConfig(
        task=row.task,
        budget=row.budget,
        seed=row.seed,
        pop_size=row.pop_size,
        offspring=row.offspring,
        mutation_rate=row.mutation_rate,
        plateau_window=row.plateau_window,
        max_generations=row.max_generations,
        mutation_strategy=row.mutation_strategy,
        mode=row.mode,  # a reclaimed/resumed run keeps its mode (baseline gate stays correct)
        seed_smiles=row.seed_smiles,  # provenance only; gen-0 is bypassed once gen_index > 0
        seed_source=row.seed_source,
        objective_json=row.objective_json,
        constraints_json=row.constraints_json,
    )


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
        # Identifies THIS registry's claims in the durable queue (m08-02) —
        # distinct per RunRegistry instance, so two registries against the same
        # DB (two API processes, or a standalone apps/runner) never collide.
        self.worker_id = f"registry-{uuid.uuid4().hex[:8]}"
        # Set by create_run_endpoint right after enqueuing, to make
        # run_worker_loop attempt a claim immediately instead of waiting out its
        # poll interval.
        self._wake: asyncio.Event = asyncio.Event()

    async def start_run(self, config: RunConfig) -> int:
        """Insert a Run row and immediately self-claim + drive it in THIS
        process — a convenience for direct/CLI-style callers (and the test
        suite) that want a run driven without going through the durable queue.
        Sets the SAME lease columns claim_next_run sets, but via a targeted
        single-row claim (not the generic scan), so it can never accidentally
        pick up an unrelated queued row sitting in a shared dev DB.

        The producer HTTP path (routes_runs.create_run_endpoint) does NOT call
        this — it only enqueues (status="queued"); a worker's claim_next_run /
        run_worker_loop is what actually drives the row."""
        async with self._sm() as session:
            run_id = await create_run(session, config)  # status="running" (default)
            await session.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(**_local_lease_fields(self.worker_id, LEASE_TTL_S))
            )
            await session.commit()
        handle = self._runs.get(run_id) or RunHandle(run_id=run_id, config=config)
        self._runs[run_id] = handle
        handle.task = asyncio.create_task(self._drive_with_lease(handle))
        return run_id

    def register_pending(self, run_id: int, config: RunConfig) -> RunHandle:
        """Pre-register a handle for a just-enqueued run, so the WS/snapshot
        layer treats it as live (``is_live`` True) immediately — before any
        worker has claimed it. This closes the async gap between "POST /runs
        enqueues" and "a worker claims + starts driving it": a subscriber that
        connects into that gap still attaches to the SAME handle object the
        eventual driver broadcasts through, so it sees every event regardless
        of exactly when the claim happens. Idempotent: returns the existing
        handle if this run_id is already registered."""
        handle = self._runs.get(run_id)
        if handle is None:
            handle = RunHandle(run_id=run_id, config=config)
            self._runs[run_id] = handle
        return handle

    def wake(self) -> None:
        """Nudge run_worker_loop to attempt a claim now rather than waiting
        out its poll interval. Called by create_run_endpoint right after
        enqueuing (when the inline worker is enabled)."""
        self._wake.set()

    def _active_run_count(self) -> int:
        """How many runs this registry is CURRENTLY driving (a live, not-yet-
        finished handle.task) — the backpressure cap's live counter."""
        return sum(1 for h in self._runs.values() if h.task is not None and not h.task.done())

    async def claim_and_drive_once(self) -> int | None:
        """Claim exactly one durable-queue-eligible run (a fresh "queued" row,
        or an abandoned "running" row whose lease expired) and drive it to
        completion in this process. Returns the claimed run_id, or None if
        nothing was claimable right now (including: this worker is already at
        MAX_CONCURRENT_RUNS — checked FIRST, before touching the DB, so a
        worker at cap never claims a row it isn't about to drive; the row
        stays "queued" for this worker's next slot or another worker).

        This is THE shared claim/lease/drive entry point: apps/runner's
        standalone worker process and the API's inline dev/test worker
        (run_worker_loop, called from both) reach the loop through here.

        Reuses a pending handle's config (attached via register_pending) when
        this process already knows about the run, so the producer's exact
        RunConfig survives without a lossy DB round-trip; otherwise (a
        crash-reclaim of a DIFFERENT worker's run, or rediscovering a stray
        queued row after a restart) reconstructs RunConfig from the persisted
        row. A run with existing Generation rows (a reclaim mid-flight)
        resumes from reconstruct_state's replayed progress instead of a fresh
        gen 0 — the SAME replay path a manual /resume uses (G6)."""
        active = self._active_run_count()
        if active >= MAX_CONCURRENT_RUNS:
            logger.debug(
                "worker %s: at capacity (%d/%d active) — refusing to claim, row(s) stay queued",
                self.worker_id,
                active,
                MAX_CONCURRENT_RUNS,
            )
            return None
        async with self._sm() as session:
            run_id = await claim_next_run(
                session, worker_id=self.worker_id, lease_ttl_s=LEASE_TTL_S
            )
            if run_id is None:
                return None
            handle = self._runs.get(run_id)
            if handle is not None:
                cfg = handle.config
            else:
                row = await session.get(Run, run_id)
                assert row is not None  # just claimed it inside this same transaction
                cfg = _config_from_row(row)
                handle = RunHandle(run_id=run_id, config=cfg)
                self._runs[run_id] = handle
            has_progress = (
                await session.scalar(
                    select(Generation.id).where(Generation.run_id == run_id).limit(1)
                )
            ) is not None
            progress = await reconstruct_state(session, run_id) if has_progress else None
        handle.task = asyncio.create_task(self._drive_with_lease(handle, progress=progress))
        return run_id

    async def run_worker_loop(self, *, poll_interval_s: float = 2.0) -> None:
        """Poll the durable queue forever: drain every currently claimable run,
        then wait for either the poll interval or a producer's wake() signal,
        whichever comes first. The SAME loop apps/runner's standalone process
        (capychem_runner) and the API's inline dev/test worker (main.py
        lifespan, gated by CAPYCHEM_INLINE_WORKER) run — one implementation,
        not two parallel copies. Runs until its task is cancelled; a single
        failed claim attempt is logged and does not kill the loop.

        The inner drain loop naturally implements backpressure: once this
        worker hits MAX_CONCURRENT_RUNS, claim_and_drive_once starts
        returning None (without touching the DB), so the drain exits and the
        loop falls through to waiting out poll_interval_s — a burst of many
        queued rows never spins up more than MAX_CONCURRENT_RUNS concurrent
        drives in this process; the rest stay queued until a slot frees."""
        while True:
            try:
                while await self.claim_and_drive_once() is not None:
                    pass
            except Exception:
                logger.exception("worker %s: claim attempt failed", self.worker_id)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=poll_interval_s)
            except TimeoutError:
                pass
            self._wake.clear()

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
                cfg = _config_from_row(row)
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
                    # Set the SAME lease columns start_run/claim_next_run set
                    # (m08-02): a resumed run must also be reclaimable if this
                    # process dies mid-drive, or it would be stranded "running"
                    # forever now that the boot-time blanket sweep is gone (see
                    # main.py).
                    lease_fields = _local_lease_fields(self.worker_id, LEASE_TTL_S)
                    for field_name, value in lease_fields.items():
                        setattr(row, field_name, value)
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
            handle.task = asyncio.create_task(self._drive_with_lease(handle, progress=progress))
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

    async def _renew_lease_loop(self, handle: RunHandle) -> None:
        """Extend this worker's lease on ``handle.run_id`` on a fixed interval,
        forever — cancelled by _drive_with_lease once _drive returns or raises.

        Stop-on-lost-lease (m08-02b, defense in depth against a revived
        zombie): if a renewal ever fails to match a row, another worker has
        already reclaimed this run (this worker's own event loop presumably
        stalled past the lease TTL and lost the race). Set the cooperative-stop
        signal so _drive exits at its next generation boundary instead of
        continuing to drive a run it no longer owns, then stop renewing.
        """
        while True:
            await asyncio.sleep(_LEASE_RENEW_INTERVAL_S)
            async with self._sm() as session:
                renewed = await renew_lease(session, handle.run_id, self.worker_id, LEASE_TTL_S)
            if not renewed:
                logger.warning(
                    "worker %s: lost lease on run %d (reclaimed elsewhere); stopping",
                    self.worker_id,
                    handle.run_id,
                )
                handle.cancel.set()
                return

    async def _drive_with_lease(
        self, handle: RunHandle, progress: dict[str, Any] | None = None
    ) -> None:
        """Wrap _drive with the durable-queue lease protocol (m08-02): renew
        the lease on a heartbeat while driving, then release it once _drive
        reaches a terminal state.

        Deliberately does NOT release the lease if _drive is interrupted by
        cancellation (a graceful process shutdown — main.py's lifespan cancels
        every handle.task before disposing the engine): _drive's own
        try/except only reaches finalize_run on its happy/fault paths, never
        on CancelledError, so an interrupted run's row is still "running", not
        terminal. Releasing the lease here would set lease_expires_at to NULL,
        which can never satisfy claim_next_run's ``< now()`` comparison —
        stranding the row unclaimable forever. Leaving the (unexpired) lease
        in place instead lets it time out naturally, after which the normal
        reclaim path picks the run back up and resumes it via
        reconstruct_state — no separate boot-time sweep required.
        """
        renew_task = asyncio.create_task(self._renew_lease_loop(handle))
        try:
            await self._drive(handle, progress=progress)
        finally:
            renew_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await renew_task
        # Reached only if _drive returned normally (see the cancellation note
        # above) — by construction it has already finalized the row to a
        # terminal status before returning. worker_id-scoped (m08-02b): a
        # revived zombie whose finalize was fenced off (lease already
        # reclaimed) must not clear the new owner's lease either.
        async with self._sm() as session:
            await release_run(session, handle.run_id, worker_id=self.worker_id)

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
            # benchmark|exploratory (07-01): gates the persistent oracle-score cache
            # (m08-04) in the score node. Static per run -- carried directly from cfg,
            # not from `prog`, so a resume keeps the same mode a fresh run would.
            "mode": cfg.mode,
            # Operator bring-your-own compounds (07-02): used only at a fresh run's
            # gen 0. On a resume, gen_index > 0 bypasses the gen-0 branch, so this is
            # inert there (cfg.seed_smiles is carried for provenance only).
            "seed_smiles": cfg.seed_smiles,
            # Composed exploratory objective (07-04); None -> benchmark scoring. Used
            # by the score node every generation (not just gen 0), so it's threaded
            # for both fresh runs and resumes.
            "objective_json": cfg.objective_json,
            # Hard constraints (07-04b); None -> no filtering. Also every-generation.
            "constraints_json": cfg.constraints_json,
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
        # instead of erasing it (a paused run's partial results
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
                        # Cross-process fan-out (m08-03): the hypothesis row already
                        # committed inside the graph's analyze node, before this state
                        # was yielded — notify AFTER that persistence, never before.
                        async with self._sm() as session:
                            await _notify_best_effort(
                                session,
                                handle.run_id,
                                "analyzer.hypothesis",
                                index=rec["after_generation_index"],
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
                        # Cross-process fan-out (m08-03): notify AFTER the RunCost
                        # upsert (and the generation's Candidates/OracleCalls, already
                        # committed by the graph's persist node) are durable.
                        await _notify_best_effort(
                            session,
                            handle.run_id,
                            "generation.complete",
                            index=snap["generation_index"],
                        )
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
            # than losing work, instead of falling through to the
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
                    seed_pop=final_state.get("seed_pop"),  # novelty vs the gen-0 seed (07-08)
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
                    seed_pop=final_state.get("seed_pop"),  # novelty vs the gen-0 seed (07-08)
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
                    seed_pop=final_state.get("seed_pop"),  # novelty vs the gen-0 seed (07-08)
                )
        # Persist the run's Langfuse trace id in summary_json so the run-detail
        # view can deep-link to it (FR-014). No schema change — summary_json is an
        # existing JSON column. None when Langfuse is off or the run errored.
        if summary is not None and run_trace_id is not None:
            summary = {**summary, "trace_id": run_trace_id}
        # Reproducibility manifest (07-06, OD-5): pin code + model + oracle + config +
        # trace. pytdc_version is cached (one probe per process); git_sha/model are
        # best-effort. Built once, at finalize.
        manifest = build_manifest(
            cfg,
            git_sha=_git_sha(),
            model_id=proposer.llm_model(),
            pytdc_version=pytdc_version(),
            trace_url=config.trace_url(run_trace_id),
        )
        async with self._sm() as session:
            # owner_worker_id fences this write (m08-02b): a revived zombie
            # whose lease was reclaimed while it kept driving must not
            # overwrite the reclaiming owner's terminal row.
            await finalize_run(
                session,
                handle.run_id,
                {"stop_reason": status, "summary": summary},
                manifest=manifest,
                owner_worker_id=self.worker_id,
            )
            # Cross-process fan-out (m08-03): notify unconditionally, even if the
            # write above was fenced off as a no-op (a revived zombie racing a
            # reclaiming owner) — a receiver re-reads whichever row is now
            # current, so a redundant notify from the losing side is harmless.
            await _notify_best_effort(session, handle.run_id, "run.complete")
        trace.flush()
        if handle.snapshot is not None:
            handle.snapshot["status"] = status  # terminal status for a post-completion GET
            # Overlay the finalize-only trust fields so a post-completion GET on the live
            # snapshot carries per-candidate quality + diversity/novelty (07-08). The
            # handle is never evicted, so the live path shadows the DB path for these.
            if summary is not None:
                handle.snapshot["top_k"] = summary.get("top_k", handle.snapshot["top_k"])
                handle.snapshot["diversity"] = summary.get("diversity")
                handle.snapshot["novelty"] = summary.get("novelty")
        terminal = RunCompleteEvent(
            run_id=handle.run_id, status=status, summary=summary
        ).model_dump()
        handle.terminal_event = terminal  # replay source for late WS subscribers
        handle.broadcast(terminal)
        # The handle stays in the registry (never evicted) so a post-completion GET/WS
        # reads the terminal in-memory snapshot. Acceptable for single-user MVP.
