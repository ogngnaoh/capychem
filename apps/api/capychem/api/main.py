"""CapyChem FastAPI backend — REST + WebSocket host for the in-process loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from capychem.api.config import ALLOWED_ORIGINS
from capychem.api.routes_catalog import router as catalog_router
from capychem.api.routes_molecule import router as molecule_router
from capychem.api.routes_runs import router as runs_router
from capychem.api.runner import RunRegistry
from capychem.api.ws_runs import router as ws_router
from capychem.db.migrate import run_migrations
from capychem.db.session import make_engine, make_sessionmaker
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
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
        await engine.dispose()


app = FastAPI(title="CapyChem API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(runs_router)
app.include_router(ws_router)
app.include_router(catalog_router)
app.include_router(molecule_router)


@app.get("/healthz")
async def healthz(request: Request) -> dict[str, str]:
    engine: AsyncEngine = request.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    return {"status": "ok"}
