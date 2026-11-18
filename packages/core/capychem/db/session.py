"""Async engine, sessionmaker, and database bootstrap.

Reads CAPYCHEM_DATABASE_URL (asyncpg driver). Real schema changes go through
Alembic migrations (see capychem.db.migrate.run_migrations, used by the API
lifespan) — `uv run alembic upgrade head`. The CLI and PostgreSQL test fixtures
use that same migration path through init_schema. Only isolated SQLite test
databases use metadata.create_all, which does not ALTER existing tables.
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
    # pool_pre_ping=True (S6): a managed Postgres (Neon/Supabase, SPEC §5) drops
    # idle connections; pre_ping issues a cheap SELECT 1 before handing a pooled
    # connection out and transparently reconnects on failure, instead of the
    # caller hitting a stale-connection error on its first real query. Adds one
    # round-trip per checkout, not per query, and is a no-op difference for the
    # in-memory-sqlite fast tests.
    resolved = url or database_url()
    # Legacy Run timestamps are naive UTC. PostgreSQL casts between timestamp
    # and timestamptz in its session timezone, so a host-local database timezone
    # otherwise shifts lease comparisons. Explicit UTC also makes exports and
    # new timezone-aware Experiment timestamps consistent across installations.
    connection_args = (
        {"server_settings": {"timezone": "UTC"}}
        if resolved.startswith("postgresql+asyncpg:")
        else {}
    )
    return create_async_engine(
        resolved, future=True, pool_pre_ping=True, connect_args=connection_args
    )


async def init_schema(engine: AsyncEngine) -> None:
    """Migrate PostgreSQL; create tables for lightweight SQLite test databases."""
    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # Deferred import avoids the migration module's database_url import
            # cycle. Use this connection, including any isolated test search_path.
            from capychem.db.migrate import upgrade_schema

            await conn.run_sync(upgrade_schema)
        else:
            await conn.run_sync(Base.metadata.create_all)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
