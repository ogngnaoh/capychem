"""/readyz vs /healthz (milestone 08 slice 06).

/healthz is bare liveness (SELECT 1); /readyz additionally proves the durable
queue's claim-shaped query runs cleanly against the ``runs`` table. The
unhealthy case is a genuine unit test: it points ``app.state.engine`` at an
unreachable DSN directly (bypassing the app lifespan entirely, so it needs no
real Postgres down and runs alongside the rest of the suite's real-Postgres
tests without disturbing them) and asserts /readyz reports 503 while such a
low-level check can be constructed without a live server. The healthy case
uses the real lifespan (real Postgres + migrations), matching every other
apps/api test's convention.
"""

from __future__ import annotations

import httpx
import pytest
from capychem.api.main import _check_ready, app
from capychem.db.session import make_engine
from httpx_ws.transport import ASGIWebSocketTransport


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGIWebSocketTransport(app), base_url="http://test")


async def test_healthz_and_readyz_ok_when_postgres_up() -> None:
    async with app.router.lifespan_context(app):
        async with _client() as c:
            h = await c.get("/healthz")
            assert h.status_code == 200 and h.json() == {"status": "ok"}
            r = await c.get("/readyz")
            assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_readyz_503_when_postgres_unreachable() -> None:
    # Port 1 on localhost refuses connections immediately (nothing listens
    # there) -- fails fast, no real Postgres outage needed to exercise this.
    bad_engine = make_engine("postgresql+asyncpg://capychem:capychem@localhost:1/capychem")
    app.state.engine = bad_engine
    try:
        async with _client() as c:
            r = await c.get("/readyz")
            assert r.status_code == 503
    finally:
        await bad_engine.dispose()


async def test_check_ready_raises_on_bad_dsn_directly() -> None:
    """The lower-level helper itself, with no HTTP layer at all."""
    bad_engine = make_engine("postgresql+asyncpg://capychem:capychem@localhost:1/capychem")
    try:
        with pytest.raises(OSError):  # connection refused -- asyncpg raises this directly
            await _check_ready(bad_engine)
    finally:
        await bad_engine.dispose()
