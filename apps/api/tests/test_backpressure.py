"""Milestone 08 slice 05: backpressure + REST contract gaps.

Concurrency cap: real Postgres (SELECT ... FOR UPDATE SKIP LOCKED is
Postgres-only) -- shares the apps/api/tests skip guard. Idempotency-Key hits
the real app lifespan. Both share the dev-Postgres-is-shared caveat documented
in test_worker_queue.py.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from capychem.api.main import app
from capychem.api.runner import RunHandle, RunRegistry
from capychem.db.models import Run
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.run import RunConfig, create_run
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_CFG = RunConfig(
    task="qed",
    budget=8,
    seed=42,
    pop_size=6,
    offspring=6,
    mutation_rate=0.01,
    plateau_window=3,
    max_generations=3,
)


@pytest.fixture
async def sm():  # type: ignore[no-untyped-def]
    engine = make_engine()
    await init_schema(engine)
    yield make_sessionmaker(engine)
    await engine.dispose()


async def _purge_claimable(sm: async_sessionmaker[AsyncSession]) -> None:
    """Same purge as test_worker_queue.py: an unrelated leftover queued/expired
    row in the shared dev Postgres would otherwise win claim_next_run's
    oldest-first scan instead of the rows this test creates."""
    async with sm() as s:
        await s.execute(
            delete(Run).where(
                or_(
                    Run.status == "queued",
                    (Run.status == "running") & (Run.lease_expires_at < func.now()),
                )
            )
        )
        await s.commit()


# --- Concurrency cap: never over-subscribe a worker under a burst -----------


async def test_worker_never_exceeds_concurrency_cap_under_burst(
    sm, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("capychem.api.runner.MAX_CONCURRENT_RUNS", 2)
    await _purge_claimable(sm)
    async with sm() as s:
        run_ids = [await create_run(s, _CFG, status="queued") for _ in range(5)]

    release = asyncio.Event()
    active = {"n": 0, "peak": 0}

    async def fake_drive_with_lease(
        self: RunRegistry, handle: RunHandle, progress: dict[str, object] | None = None
    ) -> None:
        active["n"] += 1
        active["peak"] = max(active["peak"], active["n"])
        try:
            await release.wait()
        finally:
            active["n"] -= 1

    monkeypatch.setattr(RunRegistry, "_drive_with_lease", fake_drive_with_lease)

    registry = RunRegistry(sm)
    claimed: list[int] = []
    while True:
        rid = await registry.claim_and_drive_once()
        if rid is None:
            break
        claimed.append(rid)

    # Exactly the cap succeeds; the rest of the burst refuses to claim (stays
    # "queued" -- no 429, no error, no lost row).
    assert len(claimed) == 2
    assert set(claimed) <= set(run_ids)

    async with sm() as s:
        still_queued = (
            await s.execute(select(func.count()).select_from(Run).where(Run.status == "queued"))
        ).scalar_one()
    assert still_queued == 3

    # Let both claimed tasks actually start executing (a real event-loop tick)
    # before asserting peak concurrency -- proves the cap was never exceeded,
    # not merely that only 2 claims returned non-None.
    await asyncio.sleep(0.05)
    assert active["peak"] == 2

    release.set()
    await asyncio.gather(*(h.task for h in registry._runs.values() if h.task is not None))

    # A slot frees once the in-flight drives finish: the queue keeps draining
    # rather than starving forever ("stays queued", not lost).
    freed = await registry.claim_and_drive_once()
    assert freed is not None
    assert freed not in claimed


async def test_active_run_count_reflects_only_undone_tasks(sm) -> None:  # type: ignore[no-untyped-def]
    registry = RunRegistry(sm)
    assert registry._active_run_count() == 0

    async def _noop() -> None:
        return None

    handle = RunHandle(run_id=1, config=_CFG)
    handle.task = asyncio.create_task(_noop())
    registry._runs[1] = handle
    assert registry._active_run_count() == 1
    await handle.task
    assert registry._active_run_count() == 0


# --- GET /runs pagination (REST-level smoke; pure logic covered in
# test_runs_list.py) --------------------------------------------------------


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGIWebSocketTransport(app), base_url="http://test")


async def test_get_runs_default_has_no_pagination_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPYCHEM_INLINE_WORKER", "0")
    async with app.router.lifespan_context(app):
        async with _client() as c:
            r = await c.get("/runs")
            assert r.status_code == 200
            assert isinstance(r.json(), list)  # unchanged shape: a plain array
            assert "x-next-cursor" not in {k.lower() for k in r.headers}


async def test_get_runs_paginates_with_stable_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keyset pagination must be stable under a concurrent insert: walking every
    page (through an insert landing mid-walk) reproduces the pre-insert full
    ordering AS A PREFIX -- no row shifted into a page twice, none skipped. The
    newly-inserted row (newest started_at, ascending sort) legitimately appears
    appended at the tail of a later page; that isn't a violation -- it lands
    strictly after every row the walk had already committed to. Robust to
    whatever else already exists in the shared dev Postgres (never assumes
    these are the only rows)."""
    monkeypatch.setenv("CAPYCHEM_INLINE_WORKER", "0")
    async with app.router.lifespan_context(app):
        async with app.state.sessionmaker() as session:
            for _ in range(2):  # guarantee at least 2 rows regardless of prior DB history
                await create_run(session, _CFG, status="exhausted")

        async with _client() as c:
            full_before = [
                item["run_id"]
                for item in (
                    await c.get("/runs", params={"sort": "started_at", "order": "asc"})
                ).json()
            ]
            assert len(full_before) >= 2

            collected: list[int] = []
            cursor: str | None = None
            inserted = False
            while True:
                params: dict[str, str | int] = {"sort": "started_at", "order": "asc", "limit": 1}
                if cursor is not None:
                    params["cursor"] = cursor
                r = await c.get("/runs", params=params)
                assert r.status_code == 200
                page = r.json()
                if not page:
                    break
                collected.extend(item["run_id"] for item in page)
                cursor = r.headers.get("x-next-cursor")
                if not inserted:
                    # A NEW run lands mid-walk -- must not perturb the series
                    # already committed to by earlier pages.
                    async with app.state.sessionmaker() as session:
                        await create_run(session, _CFG, status="exhausted")
                    inserted = True
                if cursor is None:
                    break

    assert collected[: len(full_before)] == full_before
    assert len(collected) == len(set(collected))  # no duplicates anywhere, including the tail


# --- POST /runs Idempotency-Key ----------------------------------------------

_BODY = {"task": "qed", "budget": 40, "seed": 42, "pop_size": 20, "offspring": 10}


async def test_post_runs_same_idempotency_key_yields_one_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPYCHEM_INLINE_WORKER", "0")  # only the intake contract is under test
    key = f"idem-{uuid.uuid4().hex}"
    async with app.router.lifespan_context(app):
        async with _client() as c:
            r1 = await c.post("/runs", json=_BODY, headers={"Idempotency-Key": key})
            assert r1.status_code == 201
            run_id_1 = r1.json()["run_id"]

            r2 = await c.post("/runs", json=_BODY, headers={"Idempotency-Key": key})
            assert r2.status_code == 201  # idempotent replay, not an error
            run_id_2 = r2.json()["run_id"]
        assert run_id_1 == run_id_2

        async with app.state.sessionmaker() as session:
            count = await session.scalar(
                select(func.count()).select_from(Run).where(Run.idempotency_key == key)
            )
    assert count == 1


async def test_post_runs_concurrent_same_idempotency_key_yields_exactly_one_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPYCHEM_INLINE_WORKER", "0")
    key = f"idem-race-{uuid.uuid4().hex}"
    async with app.router.lifespan_context(app):
        async with _client() as c:
            r1, r2 = await asyncio.gather(
                c.post("/runs", json=_BODY, headers={"Idempotency-Key": key}),
                c.post("/runs", json=_BODY, headers={"Idempotency-Key": key}),
            )
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["run_id"] == r2.json()["run_id"]

        async with app.state.sessionmaker() as session:
            count = await session.scalar(
                select(func.count()).select_from(Run).where(Run.idempotency_key == key)
            )
    assert count == 1


async def test_post_runs_without_key_is_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPYCHEM_INLINE_WORKER", "0")  # only the intake contract is under test
    async with app.router.lifespan_context(app):
        async with _client() as c:
            r1 = await c.post("/runs", json=_BODY)
            r2 = await c.post("/runs", json=_BODY)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["run_id"] != r2.json()["run_id"]  # no key -> unchanged always-enqueue
