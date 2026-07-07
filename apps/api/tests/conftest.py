"""Shared pytest fixtures for the apps/api test suite.

apps/api tests are integration tests by construction: most spin up the real
FastAPI lifespan (real Postgres via ``make_engine`` + Alembic migrations) and
drive the real LangGraph loop (real QED scoring via the isolated harness
subprocess). On a bare clone — no Postgres reachable, no ``harness/.venv``
built — those tests would otherwise ERROR (lifespan can't connect) or FAIL
(the loop pauses on ``HarnessError`` instead of completing).

Mirrors ``packages/core/tests/conftest.py``'s harness-availability check and
adds a Postgres-reachability check; ``pytest_collection_modifyitems`` skips
every test collected under this directory when either dependency is missing,
so ``uv run pytest`` stays green (SKIP, not ERROR/FAIL) on a fresh checkout.
When both are reachable (this dev env), nothing is skipped and the suite runs
unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def harness_available() -> bool:
    """True iff the legacy harness interpreter is reachable, mirroring how
    oracle.py locates it: the CAPYCHEM_HARNESS_PYTHON override, else the default
    harness/.venv/bin/python under the repo root."""
    override = os.environ.get("CAPYCHEM_HARNESS_PYTHON")
    if override:
        return Path(override).exists()
    # apps/api/tests/conftest.py -> repo root is parents[3].
    default = Path(__file__).resolve().parents[3] / "harness" / ".venv" / "bin" / "python"
    return default.exists()


def postgres_available(timeout_s: float = 2.0) -> bool:
    """True iff the configured Postgres (CAPYCHEM_DATABASE_URL, default
    localhost:5432) accepts a real connection within ``timeout_s``. Exercises the
    same sync psycopg URL Alembic's migration runner uses (capychem.db.migrate),
    so a reachable-but-wrong-credentials or unparsable URL both report False."""
    try:
        from capychem.db.migrate import sync_database_url
        from sqlalchemy import create_engine, text

        engine = create_engine(
            sync_database_url(), connect_args={"connect_timeout": int(timeout_s)}
        )
        try:
            with engine.connect() as conn:
                conn.execute(text("select 1"))
        finally:
            engine.dispose()
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip every apps/api test when Postgres or the harness venv is unreachable.

    Runs once per session at collection time — before any lifespan connect or
    harness subprocess call happens — so a bare clone reports SKIPs, not
    ERRORs/FAILUREs. When both dependencies are present, this is a no-op and
    the suite behaves exactly as it did before this hook existed.
    """
    pg_ok = postgres_available()
    harness_ok = harness_available()
    if pg_ok and harness_ok:
        return

    missing = []
    if not pg_ok:
        missing.append("Postgres unreachable (CAPYCHEM_DATABASE_URL)")
    if not harness_ok:
        missing.append("harness venv missing (CAPYCHEM_HARNESS_PYTHON / harness/.venv)")
    reason = "apps/api integration tests need a real Postgres + harness env: " + "; ".join(
        missing
    )
    marker = pytest.mark.skip(reason=reason)

    here = Path(__file__).resolve().parent
    for item in items:
        item_path = Path(str(item.path)).resolve()
        if item_path == here or here in item_path.parents:
            item.add_marker(marker)
