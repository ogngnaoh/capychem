"""Cross-process benchmark events via Postgres LISTEN/NOTIFY.

When a run is driven by a standalone
``apps/runner`` worker process, the FastAPI process serving a WS subscriber may
never hold that run's in-memory ``RunHandle`` — its ``broadcast()`` has nobody
local to reach. Postgres LISTEN/NOTIFY is the cross-process transport (no
separate message broker): the driver
NOTIFYs after each event it persists, and every API process LISTENs and fans
the notification out to its own local WS subscribers.

Channel design — ONE shared channel (``run_events``), not one channel per run:
a per-run channel (``run_events_{id}``) would need the listening connection to
dynamically LISTEN/UNLISTEN as WS clients subscribe/unsubscribe — tracking a
per-run ref-count so a still-connected second subscriber isn't stranded by a
first subscriber's UNLISTEN, plus a LISTEN round-trip for every new run. The
shared channel avoids all of that: one asyncpg connection LISTENs for the
whole process lifetime; every notification carries ``run_id`` in its payload,
and this module's in-process dict fans it out to the right local queues. The
cost is that every API process receives every run's traffic system-wide — at
CapyChem's intended single-digit-concurrent-runs scale that's a JSON-decode +
dict lookup per generation, not a scaling concern.

Payload is a small POINTER, never the event body: a NOTIFY payload has an
~8000-byte limit, and a generation.complete event's top_k (up to 10 molecules)
can approach or exceed it. The receiver re-reads the real event from Postgres
— already the source of truth for the DB-snapshot/replay path — keyed by the
pointer's run_id (see ``ws_runs.py``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Literal

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

logger = logging.getLogger(__name__)

CHANNEL = "run_events"

EventKind = Literal["generation.complete", "analyzer.hypothesis", "run.complete"]


@dataclass(frozen=True)
class RunEventPointer:
    """The NOTIFY payload: which run, what kind of event, and (for
    generation.complete / analyzer.hypothesis) the generation index it's
    about — never the event body itself."""

    run_id: int
    kind: EventKind
    index: int | None = None

    def encode(self) -> str:
        return json.dumps({"run_id": self.run_id, "kind": self.kind, "index": self.index})

    @staticmethod
    def decode(payload: str) -> RunEventPointer:
        data = json.loads(payload)
        return RunEventPointer(run_id=data["run_id"], kind=data["kind"], index=data.get("index"))


async def notify_run_event(
    session: AsyncSession, run_id: int, kind: EventKind, index: int | None = None
) -> None:
    """pg_notify a pointer to a just-persisted event.

    Callers issue this AFTER the write that made the event durable has
    committed — the pointer is worthless if the DB a receiver re-reads from
    doesn't have it yet. Commits its own tiny transaction (pg_notify has no
    durable state of its own to roll back).
    """
    pointer = RunEventPointer(run_id=run_id, kind=kind, index=index)
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHANNEL, "payload": pointer.encode()},
    )
    await session.commit()


def _asyncpg_dsn(sqlalchemy_url: str) -> str:
    """CAPYCHEM_DATABASE_URL uses the asyncpg SQLAlchemy dialect
    (``postgresql+asyncpg://...``); ``asyncpg.connect`` wants the bare libpq
    DSN (``postgresql://...``)."""
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class RunEventBus:
    """One dedicated asyncpg LISTEN connection per process, fanning
    ``run_events`` notifications out to local per-``run_id`` asyncio.Queue
    subscribers.

    SQLAlchemy's async engine cannot expose LISTEN cleanly (pooled connections,
    no persistent-notification callback API), so this holds its own raw
    asyncpg connection, independent of the app's SQLAlchemy engine. Lifecycle:
    ``start()`` once at app boot, ``stop()`` at shutdown (see main.py's
    lifespan).
    """

    def __init__(self, database_url: str) -> None:
        self._dsn = _asyncpg_dsn(database_url)
        self._conn: asyncpg.Connection | None = None
        self._subscribers: dict[int, set[asyncio.Queue[RunEventPointer]]] = {}

    async def start(self) -> None:
        self._conn = await asyncpg.connect(self._dsn)
        await self._conn.add_listener(CHANNEL, self._on_notify)

    async def stop(self) -> None:
        if self._conn is not None:
            await self._conn.remove_listener(CHANNEL, self._on_notify)
            await self._conn.close()
            self._conn = None

    def _on_notify(self, connection: object, pid: int, channel: str, payload: str) -> None:
        try:
            pointer = RunEventPointer.decode(payload)
        except (ValueError, KeyError, TypeError):
            logger.warning("run_events: dropped malformed notify payload: %r", payload)
            return
        for q in list(self._subscribers.get(pointer.run_id, ())):
            q.put_nowait(pointer)

    def subscribe(self, run_id: int) -> asyncio.Queue[RunEventPointer]:
        q: asyncio.Queue[RunEventPointer] = asyncio.Queue()
        self._subscribers.setdefault(run_id, set()).add(q)
        return q

    def unsubscribe(self, run_id: int, q: asyncio.Queue[RunEventPointer]) -> None:
        subs = self._subscribers.get(run_id)
        if subs is None:
            return
        subs.discard(q)
        if not subs:
            del self._subscribers[run_id]


def event_bus_of(conn: HTTPConnection) -> RunEventBus:
    """App-state accessor mirroring routes_runs.registry_of / sessionmaker_of."""
    bus: RunEventBus = conn.app.state.event_bus
    return bus
