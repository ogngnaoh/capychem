"""WebSocket: /ws/runs/{id}. Pushes run events; heartbeats to keep the socket warm.

Snapshot-on-load is the REST GET's job; the WS streams only NEW events. A run that
is already terminal at connect time gets a single run.complete + close, so a late
client isn't left hanging (completed handles stay in the registry, so the stored
terminal_event — not the DB — is the in-process replay source; the DB covers runs
from a previous process).
"""

from __future__ import annotations

import asyncio
from typing import Any

from capychem.api.routes_runs import registry_of, sessionmaker_of
from capychem.db.models import Run
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

_HEARTBEAT_S = 15.0


@router.websocket("/ws/runs/{run_id}")
async def ws_run(websocket: WebSocket, run_id: int) -> None:
    await websocket.accept()
    reg = registry_of(websocket)
    if not reg.is_live(run_id):
        # Never lived in this process: replay terminal state from the DB row.
        sm = sessionmaker_of(websocket)
        async with sm() as session:
            row = await session.get(Run, run_id)
        if row is None:
            await websocket.close(code=4404)
            return
        await websocket.send_json(
            {
                "type": "run.complete",
                "run_id": run_id,
                "status": row.status,
                "summary": row.summary_json,
            }
        )
        await websocket.close()
        return

    # Subscribe BEFORE the terminal check so there is no missed-event window
    # between checking and subscribing.
    queue = reg.subscribe(run_id)
    try:
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
    except WebSocketDisconnect:
        # Client went away (raised from receive or a failed send); the socket is
        # already gone, so there is nothing left to close.
        return
    finally:
        reg.unsubscribe(run_id, queue)
    await websocket.close()
