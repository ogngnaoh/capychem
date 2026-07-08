"""Milestone 08 slice 02: durable job queue + out-of-process worker.

Real Postgres (SELECT ... FOR UPDATE SKIP LOCKED is Postgres-only) — these tests
share the apps/api/tests skip guard (Postgres + harness reachable).
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from capychem.api.main import app
from capychem.api.runner import RunHandle, RunRegistry
from capychem.db.models import Generation, Run
from capychem.db.queue import claim_next_run
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.run import RunConfig, create_run
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy import delete, func, or_, select, update
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
    engine = make_engine()  # real Postgres (matches existing api tests)
    await init_schema(engine)
    yield make_sessionmaker(engine)
    await engine.dispose()


async def _purge_claimable(sm: async_sessionmaker[AsyncSession]) -> None:
    """Delete any pre-existing claimable row (queued, or "running" with an
    expired lease) before a generic-claim test runs. The dev Postgres is
    SHARED across the whole suite (see apps/api/tests/test_api.py's
    docstring) — a leftover row from an earlier test (or an earlier, failed
    run of this same file) would otherwise be the OLDEST claimable row and
    win claim_next_run's scan instead of the row this test just created,
    making the test's outcome depend on unrelated DB history."""
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


# --- Contention: two workers race one queued row ------------------------------


async def test_concurrent_claim_exactly_one_wins_no_double_execution(sm) -> None:  # type: ignore[no-untyped-def]
    await _purge_claimable(sm)
    async with sm() as s:
        run_id = await create_run(s, _CFG, status="queued")

    async def _claim(worker_id: str) -> int | None:
        async with sm() as s:
            return await claim_next_run(s, worker_id=worker_id, lease_ttl_s=60)

    a, b = await asyncio.gather(_claim("worker-a"), _claim("worker-b"))
    winners = [x for x in (a, b) if x is not None]
    losers = [x for x in (a, b) if x is None]
    assert winners == [run_id], f"expected exactly one claim to win with {run_id}, got {(a, b)}"
    assert losers == [None], f"expected exactly one refusal (None), got {(a, b)}"

    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row is not None
    assert row.status == "running"
    assert row.lease_owner in ("worker-a", "worker-b")

    # Drive the claimed run via the IDENTICAL lease-wrapped path a real worker
    # uses, then confirm no duplicate Generation.index resulted from the race.
    registry = RunRegistry(sm)
    handle = RunHandle(run_id=run_id, config=_CFG)
    registry._runs[run_id] = handle
    handle.task = asyncio.create_task(registry._drive_with_lease(handle))
    await handle.task

    async with sm() as s:
        indices = (
            await s.execute(select(Generation.index).where(Generation.run_id == run_id))
        ).scalars().all()
    assert len(indices) == len(set(indices)), f"duplicate Generation.index: {sorted(indices)}"
    assert len(indices) >= 1


# --- Producer: POST /runs enqueues; the request handler never drives it -------


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGIWebSocketTransport(app), base_url="http://test")


_BODY = {"task": "qed", "budget": 40, "seed": 42, "pop_size": 20, "offspring": 10}


async def test_post_runs_enqueues_and_does_not_drive_synchronously(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Disable the inline worker: nothing in this process will ever claim the
    # row, so if the request handler itself drove the loop, we would see it
    # here. Its absence is the proof "no create_task in the handler" holds.
    monkeypatch.setenv("CAPYCHEM_INLINE_WORKER", "0")
    async with app.router.lifespan_context(app):
        async with _client() as c:
            r = await c.post("/runs", json=_BODY)
            assert r.status_code == 201
            assert r.json()["status"] == "queued"
            run_id = r.json()["run_id"]
        async with app.state.sessionmaker() as session:
            row = await session.get(Run, run_id)
            gens = (
                await session.execute(select(Generation).where(Generation.run_id == run_id))
            ).scalars().all()
    assert row is not None
    assert row.status == "queued"  # never claimed
    assert row.lease_owner is None
    assert gens == []  # no generation was ever driven by the request handler


# --- Crash-reclaim: worker A dies mid-run, worker B reclaims + finishes -------


async def test_crash_reclaim_resumes_to_same_terminal_state(sm) -> None:  # type: ignore[no-untyped-def]
    # (a) An uninterrupted baseline run, for the G6 comparison below.
    baseline_registry = RunRegistry(sm)
    baseline_id = await baseline_registry.start_run(_CFG)
    await baseline_registry._runs[baseline_id].task
    async with sm() as s:
        baseline_row = await s.get(Run, baseline_id)
    assert baseline_row is not None and baseline_row.summary_json is not None

    # (b) Enqueue + worker A claims it and drives at least one generation.
    await _purge_claimable(sm)
    async with sm() as s:
        run_id = await create_run(s, _CFG, status="queued")
    worker_a = RunRegistry(sm)
    claimed = await worker_a.claim_and_drive_once()
    assert claimed == run_id
    handle_a = worker_a._runs[run_id]
    queue = worker_a.subscribe(run_id)
    async with asyncio.timeout(60):
        while (await queue.get())["type"] != "generation.complete":
            pass

    # Simulate worker A's death: abruptly cancel its driving task (no
    # finalize, no graceful lease release — the row is left "running"), then
    # force its lease into the past (standing in for real TTL expiry after a
    # crash, without waiting it out in the test).
    assert handle_a.task is not None
    handle_a.task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await handle_a.task
    async with sm() as s:
        await s.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(lease_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1))
        )
        await s.commit()
    async with sm() as s:
        row_mid = await s.get(Run, run_id)
    assert row_mid is not None and row_mid.status == "running"  # not finalized by the "crash"

    # (c) Worker B reclaims the SAME run (a different worker_id) and drives it
    # to completion via reconstruct_state's replay of worker A's partial progress.
    worker_b = RunRegistry(sm)
    reclaimed = await worker_b.claim_and_drive_once()
    assert reclaimed == run_id
    handle_b = worker_b._runs[run_id]
    assert handle_b.task is not None
    await handle_b.task

    async with sm() as s:
        row = await s.get(Run, run_id)
        indices = (
            await s.execute(select(Generation.index).where(Generation.run_id == run_id))
        ).scalars().all()
    assert row is not None
    assert row.status not in {"paused", "errored"}
    assert len(indices) == len(set(indices)), f"duplicate Generation.index: {sorted(indices)}"

    # G6: the crash-reclaimed run reaches the SAME terminal state the
    # uninterrupted baseline reached — same stop reason, same unique-call
    # count, same generation count, same top-k population.
    assert row.status == baseline_row.status
    assert row.summary_json is not None
    assert row.summary_json["oracle_calls"] == baseline_row.summary_json["oracle_calls"]
    assert row.summary_json["generations"] == baseline_row.summary_json["generations"]
    assert row.summary_json["top_k"] == baseline_row.summary_json["top_k"]
