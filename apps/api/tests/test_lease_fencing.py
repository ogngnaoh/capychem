"""Milestone 08 slice 02b: lease fencing against a REVIVED ZOMBIE writer.

True process DEATH is already covered by test_worker_queue.py's crash-reclaim
test (the dead worker's task is cancelled before reclaim). The gap this file
closes: a worker whose event loop merely STALLED past its lease TTL, got
reclaimed by another worker, then resumed running -- its task is never
cancelled, so without the structural + ownership-scoped fences it could still
(a) write a duplicate Generation row for an index the new owner already used,
and (b) clobber the new owner's terminal Run row via finalize/release.

Real Postgres (UNIQUE constraint enforcement + lease-owner-scoped UPDATEs) --
these tests share the apps/api/tests skip guard (Postgres + harness
reachable) and the dev Postgres is SHARED across the whole suite (see
test_worker_queue.py's docstring), hence the same claimable-row purge before
each claim.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from capychem.db.models import Generation, Run
from capychem.db.queue import claim_next_run, release_run, renew_lease
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.run import RunConfig, create_run, finalize_run
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
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
    """Same purge as test_worker_queue.py: delete any pre-existing claimable
    row before a claim, so an unrelated leftover row never wins the scan
    instead of the row this test just created."""
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


async def _expire_lease(sm: async_sessionmaker[AsyncSession], run_id: int) -> None:
    """Force a run's lease into the past -- standing in for real TTL expiry
    without waiting it out. Unlike test_worker_queue.py's crash-reclaim setup,
    the original owner's task is deliberately NEVER cancelled here: it is
    still, technically, alive (a stalled-not-dead "zombie")."""
    async with sm() as s:
        await s.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(lease_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1))
        )
        await s.commit()


async def test_renew_lease_returns_bool_by_ownership(sm) -> None:  # type: ignore[no-untyped-def]
    await _purge_claimable(sm)
    async with sm() as s:
        run_id = await create_run(s, _CFG, status="queued")
    async with sm() as s:
        claimed = await claim_next_run(s, worker_id="worker-a", lease_ttl_s=60)
    assert claimed == run_id

    async with sm() as s:
        renewed = await renew_lease(s, run_id, "worker-a", 60)
    assert renewed is True  # still the owner: the UPDATE matched a row

    async with sm() as s:
        renewed_by_stranger = await renew_lease(s, run_id, "worker-b", 60)
    assert renewed_by_stranger is False  # not the owner: zero rows matched


async def test_zombie_double_write_rejected_and_finalize_does_not_clobber(
    sm,  # type: ignore[no-untyped-def]
) -> None:
    # (a) Worker A claims the run and persists generation 0 -- standing in for
    # a partial drive before its event loop stalls.
    await _purge_claimable(sm)
    async with sm() as s:
        run_id = await create_run(s, _CFG, status="queued")
    async with sm() as s:
        claimed = await claim_next_run(s, worker_id="worker-a", lease_ttl_s=60)
    assert claimed == run_id
    async with sm() as s:
        s.add(Generation(run_id=run_id, index=0, proposer_used="starting"))
        await s.commit()

    # (b) A's lease expires (its event loop stalled past the TTL) WITHOUT its
    # task ever being cancelled -- it is still, technically, running. Worker B
    # reclaims the SAME run.
    await _expire_lease(sm, run_id)
    async with sm() as s:
        reclaimed = await claim_next_run(s, worker_id="worker-b", lease_ttl_s=60)
    assert reclaimed == run_id
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row is not None and row.lease_owner == "worker-b"

    # (c) B persists ITS generation 1.
    async with sm() as s:
        s.add(Generation(run_id=run_id, index=1, proposer_used="graph_ga"))
        await s.commit()

    # (d) The revived zombie A -- unaware it lost the lease -- resumes and
    # tries to persist a generation at the SAME index B already wrote. The
    # structural UNIQUE(run_id, index) backstop rejects it.
    async with sm() as s:
        s.add(Generation(run_id=run_id, index=1, proposer_used="llm"))
        with pytest.raises(IntegrityError):
            await s.commit()
        await s.rollback()

    async with sm() as s:
        gens = (
            (
                await s.execute(
                    select(Generation).where(Generation.run_id == run_id, Generation.index == 1)
                )
            )
            .scalars()
            .all()
        )
    assert len(gens) == 1, f"expected exactly one generation at index 1, got {len(gens)}"
    assert gens[0].proposer_used == "graph_ga"  # B's write survived; A's was rejected

    # (e) A falls into its except-Exception path (the IntegrityError surfaces
    # as a generic loop fault -- see runner.py `_drive`) and tries to finalize
    # as "errored", scoped to ITS OWN worker_id. Fenced off: A no longer owns
    # the lease, so this is a no-op.
    async with sm() as s:
        await finalize_run(
            s, run_id, {"stop_reason": "errored", "summary": None}, owner_worker_id="worker-a"
        )
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row is not None
    assert row.status == "running"  # untouched by A's fenced finalize

    # (f) A's release attempt is likewise fenced off -- B's lease survives.
    async with sm() as s:
        await release_run(s, run_id, worker_id="worker-a")
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row is not None
    assert row.lease_owner == "worker-b"

    # (g) B, the legitimate reclaiming owner, finalizes the run -- unaffected
    # by anything A attempted; its own scoped write goes through.
    async with sm() as s:
        await finalize_run(
            s,
            run_id,
            {"stop_reason": "exhausted", "summary": {"top_k": [], "generations": 2}},
            owner_worker_id="worker-b",
        )
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row is not None
    assert row.status == "exhausted"
    assert row.summary_json == {"top_k": [], "generations": 2}

    # (h) B's release succeeds -- it is the current owner.
    async with sm() as s:
        await release_run(s, run_id, worker_id="worker-b")
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row is not None and row.lease_owner is None
