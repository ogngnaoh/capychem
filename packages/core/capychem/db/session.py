"""Async engine, sessionmaker, and first-connect schema bootstrap.

metadata.create_all is fine while the greenfield schema churns (slice 2); Alembic
arrives with the first additive change (slice 3/4). Reads CAPYCHEM_DATABASE_URL
(asyncpg driver). Dev resets are drop/recreate.
"""

from __future__ import annotations

import os

from capychem.db.models import Base
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_DEFAULT_URL = "postgresql+asyncpg://capychem:capychem@localhost:5432/capychem"


def database_url() -> str:
    return os.environ.get("CAPYCHEM_DATABASE_URL", _DEFAULT_URL)


def make_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(url or database_url(), future=True)


async def init_schema(engine: AsyncEngine) -> None:
    """Create all tables if they do not exist (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
