"""Durable job queue over the ``runs`` table (milestone 08 slice 02).

No Redis/broker/Celery — Postgres is both the run store and the queue
(PROJECT.md §10 backend-headline re-decide). A "queued" row, or a "running" row
whose lease has expired (its worker presumably crashed), is claimable via
``SELECT ... FOR UPDATE SKIP LOCKED``: two concurrent claimers racing the same
row never both win, and a claimer that would block on a locked row skips it
instead of waiting.

Clock: every lease comparison and every lease-expiry write uses the DATABASE's
clock (``func.now()``), never a worker's wall clock, so skew between a worker
host and Postgres can never cause a premature or missed reclaim.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from capychem.db.models import Run
from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession


def _lease_claim_values(worker_id: str, lease_ttl_s: int) -> dict[str, Any]:
    """The 4 columns a claim sets, shared by claim_next_run's generic scan-claim
    and RunRegistry.start_run's targeted self-claim, so both write an identical
    lease shape."""
    return {
        "status": "running",
        "lease_owner": worker_id,
        "lease_expires_at": func.now() + timedelta(seconds=lease_ttl_s),
        "heartbeat_at": func.now(),
    }


async def claim_next_run(session: AsyncSession, *, worker_id: str, lease_ttl_s: int) -> int | None:
    """Atomically claim exactly one claimable run for ``worker_id``.

    Claimable = status == "queued", OR status == "running" with an expired
    lease (lease_expires_at < now() — an abandoned run from a crashed worker).
    Oldest-first (started_at) so no run starves behind a stream of newer ones.
    ``FOR UPDATE SKIP LOCKED`` means a concurrent caller racing this query on
    the same row never blocks on it or double-claims it: it skips straight to
    the next claimable row, or returns None if there isn't one.

    Returns the claimed run_id, or None if nothing is claimable right now.
    """
    stmt = (
        select(Run.id)
        .where(
            or_(
                Run.status == "queued",
                (Run.status == "running") & (Run.lease_expires_at < func.now()),
            )
        )
        .order_by(Run.started_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    run_id = (await session.execute(stmt)).scalar_one_or_none()
    if run_id is None:
        return None
    await session.execute(
        update(Run).where(Run.id == run_id).values(**_lease_claim_values(worker_id, lease_ttl_s))
    )
    await session.commit()
    return run_id


async def renew_lease(session: AsyncSession, run_id: int, worker_id: str, lease_ttl_s: int) -> bool:
    """Extend a still-owned lease's expiry + heartbeat.

    Scoped to ``lease_owner == worker_id``: if another worker already reclaimed
    this run (this worker's previous lease having expired), the UPDATE matches
    zero rows and is a no-op — a zombie renewal can never resurrect a lease it
    no longer owns.

    Returns True iff the UPDATE matched a row (this worker still owns the
    lease), False otherwise. A revived zombie (m08-02b) — a worker whose event
    loop stalled past its lease TTL, was reclaimed, then kept running — sees
    False here; the caller (RunRegistry._renew_lease_loop) uses that to stop
    driving instead of racing the new owner.
    """
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            update(Run)
            .where(Run.id == run_id, Run.lease_owner == worker_id)
            .values(
                lease_expires_at=func.now() + timedelta(seconds=lease_ttl_s),
                heartbeat_at=func.now(),
            )
        ),
    )
    await session.commit()
    return result.rowcount > 0


async def release_run(session: AsyncSession, run_id: int, *, worker_id: str | None = None) -> None:
    """Clear the lease once a run has reached a terminal status.

    ``worker_id``, when given, scopes the clear to the CURRENT lease owner
    (m08-02b): a revived zombie's release must not clear a reclaiming owner's
    lease out from under it. None (default) keeps the prior unconditional
    behavior, for callers where there is no owner left to race.

    Callers must only call this AFTER the row has actually been finalized to a
    terminal status — never on a run that is merely interrupted (e.g. a
    graceful process shutdown), since a cleared lease_expires_at (NULL) would
    never satisfy claim_next_run's ``< now()`` comparison and would strand the
    row unclaimable forever. An interrupted-but-still-"running" row is meant to
    be left alone: its (unexpired) lease naturally times out and becomes
    reclaimable through the normal path.
    """
    stmt = update(Run).where(Run.id == run_id).values(lease_owner=None, lease_expires_at=None)
    if worker_id is not None:
        stmt = stmt.where(Run.lease_owner == worker_id)
    await session.execute(stmt)
    await session.commit()
