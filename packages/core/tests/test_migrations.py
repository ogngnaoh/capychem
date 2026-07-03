"""Proves the Alembic baseline (0001_baseline.py) reproduces exactly what
Base.metadata / metadata.create_all builds today — no drift, no hand-written
schema divergence.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from capychem.db import migrate
from capychem.db.models import Base
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

_TEMP_DB = "capychem_test_migrations_baseline"


def _maintenance_url() -> str:
    """The sync (psycopg) URL for the default/admin database used to create and
    drop the throwaway test database."""
    return migrate.sync_database_url()


def _postgres_available() -> bool:
    try:
        engine = create_engine(_maintenance_url())
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        engine.dispose()
        return True
    except OperationalError:
        return False


@pytest.fixture
def temp_db_url() -> Iterator[str]:
    """Create a throwaway database, yield its sync URL, then drop it."""
    if not _postgres_available():
        pytest.skip("needs a reachable Postgres (CAPYCHEM_DATABASE_URL / infra/compose.yml)")

    admin_engine = create_engine(_maintenance_url(), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{_TEMP_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{_TEMP_DB}"'))

    temp_url = (
        make_url(_maintenance_url()).set(database=_TEMP_DB).render_as_string(hide_password=False)
    )
    try:
        yield temp_url
    finally:
        temp_engine = create_engine(temp_url)
        temp_engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{_TEMP_DB}"'))
        admin_engine.dispose()


def test_baseline_matches_models(temp_db_url: str) -> None:
    cfg = Config(str(migrate._ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", temp_db_url)

    from alembic import command

    command.upgrade(cfg, "head")

    engine = create_engine(temp_db_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            diff = compare_metadata(context, Base.metadata)
        assert diff == [], f"baseline migration diverges from Base.metadata: {diff}"
    finally:
        engine.dispose()
