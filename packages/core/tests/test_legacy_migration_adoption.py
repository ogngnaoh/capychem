"""Adopt only a proven unversioned layout, preserving existing /runs data."""

from __future__ import annotations

import os
import uuid

import pytest
from alembic import command
from capychem.db.migrate import _alembic_config, _upgrade_connection, legacy_metadata
from capychem.db.models import Run
from sqlalchemy import create_engine, inspect, select, text


@pytest.fixture
def isolated_connection():
    url = os.environ.get("CAPYCHEM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Migration adoption requires actual PostgreSQL.")
    if not url.split("?")[0].endswith("_test"):
        pytest.fail("Use a dedicated database whose name ends in _test.")
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))
    schema = f"migration_test_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            yield connection
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def existing_run(connection):
    return connection.scalar(
        Run.__table__.insert()
        .values(
            task="qed",
            budget=10,
            plateau_window=3,
            pop_size=4,
            offspring=2,
            mutation_rate=0.1,
            seed=42,
        )
        .returning(Run.id)
    )


@pytest.mark.parametrize("source", ["historical_migrations", "create_all"])
def test_adoption_keeps_runs_and_applies_new_experiment_schema(isolated_connection, source):
    connection = isolated_connection
    cfg = _alembic_config()
    cfg.attributes["connection"] = connection
    if source == "historical_migrations":
        command.upgrade(cfg, "9fa6b5f041b2")
        connection.execute(text("DROP TABLE alembic_version"))
    else:
        legacy_metadata().create_all(connection)
    run_id = existing_run(connection)
    assert "experiments" not in inspect(connection).get_table_names()

    _upgrade_connection(connection, cfg)

    tables = inspect(connection).get_table_names()
    assert {
        "experiments",
        "experiment_tasks",
        "experiment_candidates",
        "experiment_studies",
        "experiment_study_members",
    } <= set(tables)
    assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "d16324b5eac8"
    assert connection.scalar(select(Run.task).where(Run.id == run_id)) == "qed"
    # Re-running startup is a no-op and preserves the same row.
    _upgrade_connection(connection, cfg)
    assert connection.scalar(select(Run.seed).where(Run.id == run_id)) == 42


def test_ambiguous_unversioned_schema_is_rejected_without_stamp(isolated_connection):
    connection = isolated_connection
    legacy_metadata().create_all(connection)
    run_id = existing_run(connection)
    connection.execute(text("ALTER TABLE runs DROP COLUMN idempotency_key"))

    with pytest.raises(RuntimeError, match="Do not stamp it to head"):
        _upgrade_connection(connection, _alembic_config())

    tables = inspect(connection).get_table_names()
    assert "alembic_version" not in tables
    assert "experiments" not in tables
    assert connection.scalar(select(Run.task).where(Run.id == run_id)) == "qed"
