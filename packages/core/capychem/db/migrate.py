"""Alembic-driven schema bootstrap, called synchronously from the API lifespan.

Migrations run through Alembic's sync psycopg driver. Unversioned databases
are adopted only after their schema matches the last known legacy schema.
Stamp that specific revision, then apply newer migrations in one transaction;
never stamp an unknown existing database straight to the current head.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from capychem.db import models
from capychem.db.session import database_url
from sqlalchemy import Connection, MetaData, Table, create_engine, inspect

# packages/core/capychem/db/migrate.py -> repo root is parents[4].
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"
_LEGACY_REVISION = "9fa6b5f041b2"


def legacy_metadata() -> MetaData:
    """The original /runs model at the last pre-Experiment revision.

    The migration test compares this against a database created by that exact
    historical revision, so later edits to the legacy models cannot silently
    change which unversioned layout we accept.
    """
    metadata = MetaData()
    for model in (
        models.Run,
        models.Generation,
        models.Candidate,
        models.OracleCall,
        models.RunCost,
        models.OracleScoreCache,
        models.AnalyzerHypothesis,
    ):
        cast(Table, model.__table__).to_metadata(metadata)
    return metadata


def _verify_legacy_schema(connection: Connection) -> None:
    expected = legacy_metadata()
    inspector = inspect(connection)
    context = MigrationContext.configure(
        connection,
        opts={"compare_type": True, "compare_server_default": True},
    )
    differences = compare_metadata(context, expected)
    # Alembic autogeneration does not detect all primary-key changes.
    wrong_primary_keys = [
        table.name
        for table in expected.tables.values()
        if table.name in inspector.get_table_names()
        and inspector.get_pk_constraint(table.name).get("constrained_columns")
        != [column.name for column in table.primary_key.columns]
    ]
    if differences or wrong_primary_keys:
        raise RuntimeError(
            "Found an unversioned CapyChem database whose schema does not match "
            f"the known legacy revision {_LEGACY_REVISION}. No schema or data was changed. "
            "Use a new empty database, or back up this database and restore its correct "
            "Alembic revision before upgrading. Do not stamp it to head."
        )


def _upgrade_connection(connection: Connection, cfg: Config) -> None:
    cfg.attributes["connection"] = connection
    tables = inspect(connection).get_table_names()
    if "runs" in tables and "alembic_version" not in tables:
        _verify_legacy_schema(connection)
        command.stamp(cfg, _LEGACY_REVISION)
    command.upgrade(cfg, "head")


def sync_database_url() -> str:
    """CAPYCHEM_DATABASE_URL, with the async asyncpg driver swapped for the
    sync psycopg driver Alembic's migration context requires."""
    return database_url().replace("+asyncpg", "+psycopg")


def _alembic_config() -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", sync_database_url())
    return cfg


def upgrade_schema(connection: Connection) -> None:
    """Migrate a caller-owned connection, preserving its transaction and schema.

    Async engines can invoke this through ``AsyncConnection.run_sync`` so CLI
    bootstrap uses the same verified migration path as synchronous API startup.
    """
    _upgrade_connection(connection, _alembic_config())


def run_migrations() -> None:
    """Bring the schema to head. Synchronous — run off the event loop
    (e.g. via asyncio.to_thread) when called from async code.

    - Fresh DB (no `runs` table): the baseline revision creates all tables.
    - Unversioned legacy DB: verify the known legacy schema, stamp that
      specific revision, then apply new migrations. Reject ambiguous layouts.
    - Already-migrated DB: upgrade is a no-op or applies newer revisions.
    """
    url = sync_database_url()
    engine = create_engine(
        url,
        connect_args={"options": "-c timezone=UTC"} if url.startswith("postgresql") else {},
    )
    try:
        with engine.begin() as connection:
            upgrade_schema(connection)
    finally:
        engine.dispose()
