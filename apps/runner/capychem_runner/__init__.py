"""capychem_runner — the standalone out-of-process worker (milestone 08 slice 02).

A separate OS process from apps/api's FastAPI server (and from the Modal
apps/worker LLM/oracle endpoints). It claims durable-queue rows from Postgres
(``SELECT ... FOR UPDATE SKIP LOCKED``, via ``capychem.db.queue``) and drives the
existing LangGraph loop to completion, renewing a lease/heartbeat while it
runs. If the worker dies, the lease expires and a second worker (this process
restarted, or another instance) reclaims the run and resumes it via
``capychem.resume.reconstruct_state`` to the same terminal state.

Reuses ``capychem.api.runner.RunRegistry`` for the actual claim/lease/drive
code path — the IDENTICAL implementation apps/api's inline dev/test worker
runs — rather than a second copy of that state machine. This process never
starts a web server; any WS-broadcast events RunRegistry emits along the way
simply have no subscribers here (a harmless no-op) — cross-process live event
delivery to the API's WS clients is a later slice (LISTEN/NOTIFY).

Backpressure (milestone 08 slice 05): the same RunRegistry enforces
``CAPYCHEM_MAX_CONCURRENT_RUNS`` (default 4) concurrent drives per process —
a burst of many queued rows never spins up unbounded concurrent loops in a
single ``capychem_runner`` instance; the rest stay "queued" until a slot
frees or another replica claims them.

Usage: ``python -m capychem_runner``
"""

from __future__ import annotations

import asyncio
import logging
import os

from capychem.api.runner import RunRegistry
from capychem.db.migrate import run_migrations
from capychem.db.session import make_engine, make_sessionmaker
from capychem.env import load_local_env

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = float(os.environ.get("CAPYCHEM_RUNNER_POLL_S", "2.0"))


async def run_forever() -> None:
    """Boot a registry against the real DB and poll the durable queue until
    cancelled (SIGINT/SIGTERM via asyncio.run's default handling, or the
    caller cancelling the task directly in-process for a test/demo)."""
    load_local_env()
    engine = make_engine()
    await asyncio.to_thread(run_migrations)
    sessionmaker = make_sessionmaker(engine)
    registry = RunRegistry(sessionmaker)
    logger.info(
        "capychem-runner worker_id=%s starting, polling every %.1fs",
        registry.worker_id,
        _POLL_INTERVAL_S,
    )
    try:
        await registry.run_worker_loop(poll_interval_s=_POLL_INTERVAL_S)
    finally:
        await registry.shutdown()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logger.info("capychem-runner stopped")
