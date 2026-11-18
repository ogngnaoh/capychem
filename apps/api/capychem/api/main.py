"""CapyChem FastAPI backend — REST + WebSocket host for the in-process loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from capychem.api.config import ALLOWED_ORIGINS
from capychem.api.events import RunEventBus
from capychem.api.routes_catalog import router as catalog_router
from capychem.api.routes_molecule import router as molecule_router
from capychem.api.routes_runs import router as runs_router
from capychem.api.runner import RunRegistry
from capychem.api.ws_runs import router as ws_router
from capychem.db.migrate import run_migrations
from capychem.db.models import Run
from capychem.db.session import database_url, make_engine, make_sessionmaker
from capychem.experiments.routes import router as experiments_router
from capychem.experiments.studies import router as studies_router
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# Same-process convenience worker (milestone 08 slice 02), on by default for
# dev/test. Production (S6 compose) sets this "0" and runs a separate
# `apps/runner` process as the only claimer, so the API process never drives a
# loop itself.
_INLINE_WORKER_ENV = "CAPYCHEM_INLINE_WORKER"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from capychem.env import load_local_env

    load_local_env()
    engine = make_engine()
    await asyncio.to_thread(run_migrations)
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.registry = RunRegistry(app.state.sessionmaker)
    # Cross-process live events (milestone 08 slice 03): a dedicated asyncpg
    # LISTEN connection, opened once for this process's lifetime, closed at
    # shutdown alongside the engine. See capychem.api.events.RunEventBus.
    app.state.event_bus = RunEventBus(database_url())
    await app.state.event_bus.start()
    inline_worker_enabled = os.environ.get(_INLINE_WORKER_ENV, "1") != "0"
    app.state.inline_worker_enabled = inline_worker_enabled
    worker_task: asyncio.Task[None] | None = None
    if inline_worker_enabled:
        # Claims + drives durable-queue rows via the IDENTICAL claim/lease/drive
        # path a standalone apps/runner process uses (RunRegistry.run_worker_loop).
        # There is no separate boot-time "stranded running" sweep: a row left
        # "running" by a crashed process still carries an (eventually expiring)
        # lease, and claim_next_run reclaims it on its own once that lease
        # expires — self-healing, no sweep needed.
        worker_task = asyncio.create_task(app.state.registry.run_worker_loop())
    else:
        logger.info(
            "inline worker disabled (%s=0); a separate apps/runner process must "
            "claim queued runs",
            _INLINE_WORKER_ENV,
        )
    try:
        yield
    finally:
        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
        # Shut down driver tasks BEFORE disposing the engine: disposal must not
        # race in-flight drivers still holding connections.
        await app.state.registry.shutdown()
        await app.state.event_bus.stop()
        await engine.dispose()


app = FastAPI(title="CapyChem API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["*"],
)

app.include_router(runs_router)
app.include_router(ws_router)
app.include_router(catalog_router)
app.include_router(molecule_router)
app.include_router(experiments_router)
app.include_router(studies_router)


@app.get("/healthz")
async def healthz(request: Request) -> dict[str, str]:
    """Liveness: is this process up and able to reach Postgres at all."""
    engine: AsyncEngine = request.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    return {"status": "ok"}


async def _check_ready(engine: AsyncEngine) -> None:
    """Raise iff the API is not ready to serve traffic.

    Distinct from /healthz's bare ``SELECT 1``: readiness additionally proves
    the durable-queue claim query (S6, mirroring capychem.db.queue.claim_next_run's
    predicate) executes cleanly against the ``runs`` table -- i.e. Postgres is
    reachable AND the schema the queue/API depend on is actually there and
    queryable, not just that the socket connects. Read-only: never claims or
    mutates a row.
    """
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
        await conn.execute(
            select(Run.id)
            .where(
                or_(
                    Run.status == "queued",
                    (Run.status == "running") & (Run.lease_expires_at < func.now()),
                )
            )
            .limit(1)
        )


@app.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    """Readiness: Postgres reachable AND the queue's claim query works.

    A managed Postgres can drop idle connections (see pool_pre_ping on
    make_engine) or be mid-failover while the process itself is still up and
    would happily answer /healthz's liveness check -- /readyz is what an
    orchestrator's readiness probe should gate traffic/queue-claiming on.
    """
    engine: AsyncEngine = request.app.state.engine
    try:
        await _check_ready(engine)
    except Exception:
        logger.warning("readyz check failed", exc_info=True)
        raise HTTPException(status_code=503, detail="not ready") from None
    return {"status": "ok"}
