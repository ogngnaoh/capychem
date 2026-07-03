"""Alembic-driven schema bootstrap, called synchronously from the API lifespan.

Migrations run through Alembic (sync psycopg driver — the async engine's
asyncpg dialect can't run Alembic's sync migration context). A pre-Alembic
dev DB (tables present, no alembic_version row) is adopted by stamping it to
head rather than replayed, since the baseline revision reproduces exactly
what metadata.create_all already built there.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from capychem.db.session import database_url
from sqlalchemy import create_engine, inspect

# packages/core/capychem/db/migrate.py -> repo root is parents[4].
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


def sync_database_url() -> str:
    """CAPYCHEM_DATABASE_URL, with the async asyncpg driver swapped for the
    sync psycopg driver Alembic's migration context requires."""
    return database_url().replace("+asyncpg", "+psycopg")


def _alembic_config() -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", sync_database_url())
    return cfg


def run_migrations() -> None:
    """Bring the schema to head. Synchronous — run off the event loop
    (e.g. via asyncio.to_thread) when called from async code.

    - Fresh DB (no `runs` table): the baseline revision creates all tables.
    - Pre-Alembic dev DB (`runs` exists, no `alembic_version`): stamped to
      head first, so the (no-op) upgrade doesn't try to recreate tables that
      already match the baseline.
    - Already-migrated DB: upgrade is a no-op or applies newer revisions.
    """
    cfg = _alembic_config()
    engine = create_engine(sync_database_url())
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if "runs" in tables and "alembic_version" not in tables:
            command.stamp(cfg, "head")
    finally:
        engine.dispose()
    command.upgrade(cfg, "head")
