"""CapyChem FastAPI backend — REST + WebSocket host for the in-process loop."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from capychem.api.config import ALLOWED_ORIGINS
from capychem.api.routes_catalog import router as catalog_router
from capychem.api.routes_molecule import router as molecule_router
from capychem.api.routes_runs import router as runs_router
from capychem.api.runner import RunRegistry
from capychem.api.ws_runs import router as ws_router
from capychem.db.migrate import run_migrations
from capychem.db.models import Run
from capychem.db.session import make_engine, make_sessionmaker
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from capychem.env import load_local_env

    load_local_env()
    engine = make_engine()
    await asyncio.to_thread(run_migrations)
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.registry = RunRegistry(app.state.sessionmaker)
    # Sweep rows stranded `running` by a previous process: a crash/restart skips
    # finalize_run, so without this those rows claim "running" forever.
    async with app.state.sessionmaker() as session:
        res = await session.execute(
            update(Run).where(Run.status == "running").values(status="stopped")
        )
        await session.commit()
        logger.info("swept %d stranded running row(s)", res.rowcount)
    try:
        yield
    finally:
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
