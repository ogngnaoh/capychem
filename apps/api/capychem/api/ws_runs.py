"""WebSocket: /ws/runs/{id}. Pushes run events; heartbeats to keep the socket warm.

Snapshot-on-load is the REST GET's job; the WS streams only NEW events. Two
delivery paths, chosen by whether this API process is the one driving the run:

- **Local** (``reg.is_live(run_id)``): subscribe to the in-memory RunHandle's
  queue — the original single-process path, unchanged.
- **Cross-process / DB-snapshot** (milestone 08 slice 03): the run is not live
  in THIS process — either a standalone ``apps/runner`` worker (or another API
  process's inline worker) is driving it, or it hasn't been claimed yet, or it
  already finished. A terminal row still gets the single run.complete + close.
  A NON-terminal row is caught up from a DB replay (the same
  ``reconstruct_state`` resume/crash-reclaim already use) — "the DB snapshot" —
  then the socket subscribes to the ``RunEventBus`` LISTEN/NOTIFY fan-out and
  forwards each new event as it's notified, re-reading the authoritative event
  from Postgres per notify (the NOTIFY payload is a pointer, never the body).
  This is now the NORMAL path for a late/reconnecting subscriber, not a
  terminal-only special case.
"""

from __future__ import annotations

import asyncio
from typing import Any

from capychem import cost
from capychem.api.config import ALLOWED_ORIGINS
from capychem.api.events import RunEventPointer, event_bus_of
from capychem.api.routes_runs import _hypotheses_for, registry_of, sessionmaker_of
from capychem.api.schemas import (
    AnalyzerHypothesisEvent,
    AnalyzerHypothesisOut,
    GenerationCompleteEvent,
    RunCompleteEvent,
    TopMolecule,
)
from capychem.db.models import Run
from capychem.resume import reconstruct_state
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

_HEARTBEAT_S = 15.0

# Run.status is "queued" or "running" until finalize_run sets a terminal
# stop_reason (see capychem.run.finalize_run / capychem.db.queue) — these are
# the only two non-terminal values the column ever holds.
_NON_TERMINAL_STATUSES = {"queued", "running"}


async def _current_generation_event(
    session: AsyncSession, run_id: int
) -> GenerationCompleteEvent | None:
    """The generation.complete event describing progress AS OF the latest
    persisted generation, reconstructed from Candidate/Generation/RunCost rows
    via reconstruct_state — the SAME replay resume() and crash-reclaim already
    use — so a DB-driven catch-up stays consistent with what the driving
    process itself would have broadcast live. None if no generation has
    completed yet."""
    progress = await reconstruct_state(session, run_id)
    curve = progress["auc_curve"]
    if not curve:
        return None
    top = sorted(progress["population"], key=lambda m: (-m.score, m.smiles))[:10]
    return GenerationCompleteEvent(
        generation_index=len(curve),
        best_score=top[0].score if top else 0.0,
        top10_mean=curve[-1][1],
        oracle_calls_used=progress["calls_used"],
        cost_so_far_usd=await cost.run_cost_total(session, run_id),
        top_k=[TopMolecule(smiles=m.smiles, score=m.score) for m in top],
    )


def _hypothesis_event(hyp: AnalyzerHypothesisOut) -> dict[str, Any]:
    return AnalyzerHypothesisEvent(**hyp.model_dump()).model_dump()


@router.websocket("/ws/runs/{run_id}")
async def ws_run(websocket: WebSocket, run_id: int) -> None:
    # CSWSH guard: browsers attach the page's Origin to WS handshakes, and
    # CORSMiddleware does not gate WebSockets, so enforce the allowlist here.
    # A MISSING Origin is allowed — non-browser clients (curl, tests, scripts)
    # cannot be CSWSH'd; the attack requires a browser, which always sends Origin.
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    reg = registry_of(websocket)
    queue: asyncio.Queue[dict[str, Any]] | None = None
    pointer_queue: asyncio.Queue[RunEventPointer] | None = None
    try:
        if not reg.is_live(run_id):
            sm = sessionmaker_of(websocket)
            bus = event_bus_of(websocket)
            # Subscribe to the cross-process bus BEFORE any DB read, so a NOTIFY
            # fired in the gap between "check status" and "start listening" is
            # queued, not lost (mirrors the local path's subscribe-before-check).
            pointer_queue = bus.subscribe(run_id)
            last_gen_index = 0
            sent_hyp_indices: set[int] = set()
            async with sm() as session:
                row = await session.get(Run, run_id)
                if row is None:
                    await websocket.close(code=4404)
                    return
                if row.status not in _NON_TERMINAL_STATUSES:
                    # Already finished before this WS connected.
                    await websocket.send_json(
                        RunCompleteEvent(
                            run_id=run_id, status=row.status, summary=row.summary_json
                        ).model_dump()
                    )
                    await websocket.close()
                    return
                # Non-terminal: some worker (this process's own out-of-band
                # worker, a standalone apps/runner, or nobody yet) owns it. Replay
                # the DB snapshot — the catch-up this slice makes the NORMAL path
                # for a late/reconnecting subscriber — then fall through to
                # forwarding live NOTIFY-triggered events below.
                gen_event = await _current_generation_event(session, run_id)
                if gen_event is not None:
                    await websocket.send_json(gen_event.model_dump())
                    last_gen_index = gen_event.generation_index
                for hyp in await _hypotheses_for(session, run_id):
                    await websocket.send_json(_hypothesis_event(hyp))
                    sent_hyp_indices.add(hyp.after_generation_index)

            while True:
                try:
                    pointer = await asyncio.wait_for(pointer_queue.get(), timeout=_HEARTBEAT_S)
                except TimeoutError:
                    await websocket.send_json({"type": "ping"})
                    continue
                async with sm() as session:
                    if pointer.kind == "run.complete":
                        row = await session.get(Run, run_id)
                        assert row is not None  # rows are never deleted
                        await websocket.send_json(
                            RunCompleteEvent(
                                run_id=run_id, status=row.status, summary=row.summary_json
                            ).model_dump()
                        )
                        break
                    if pointer.kind == "generation.complete":
                        gen_event = await _current_generation_event(session, run_id)
                        if gen_event is not None and gen_event.generation_index > last_gen_index:
                            await websocket.send_json(gen_event.model_dump())
                            last_gen_index = gen_event.generation_index
                    elif pointer.kind == "analyzer.hypothesis":
                        for hyp in await _hypotheses_for(session, run_id):
                            if hyp.after_generation_index not in sent_hyp_indices:
                                await websocket.send_json(_hypothesis_event(hyp))
                                sent_hyp_indices.add(hyp.after_generation_index)
            await websocket.close()
            return

        # Subscribe BEFORE the terminal check so there is no missed-event window
        # between checking and subscribing.
        queue = reg.subscribe(run_id)
        # Completed handles are never evicted and the queue gets no replay, so a
        # run already terminal at connect time is served the stored terminal event.
        terminal = reg.terminal_event(run_id)
        if terminal is not None:
            await websocket.send_json(terminal)
        else:
            while True:
                try:
                    event: dict[str, Any] = await asyncio.wait_for(
                        queue.get(), timeout=_HEARTBEAT_S
                    )
                except TimeoutError:
                    await websocket.send_json({"type": "ping"})
                    continue
                await websocket.send_json(event)
                if event["type"] == "run.complete":
                    break
        await websocket.close()
    except WebSocketDisconnect:
        # This handler never calls receive(), so sends — including the 15 s
        # heartbeat ping — are the ONLY disconnect detector; removing the
        # heartbeat would also remove dead-client cleanup (worst case 15 s
        # late). A client that closed first makes any send/close raise here;
        # the socket is already gone, so there is nothing left to do.
        return
    finally:
        if queue is not None:
            reg.unsubscribe(run_id, queue)
        if pointer_queue is not None:
            event_bus_of(websocket).unsubscribe(run_id, pointer_queue)
