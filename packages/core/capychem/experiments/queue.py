"""A fixed pipeline queue with attempt-level fencing and durable events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import (
    Experiment,
    ExperimentAttempt,
    ExperimentEvent,
    ExperimentTask,
    ExperimentWorkerHeartbeat,
)


def now_value(session: AsyncSession) -> Any:
    return (
        datetime.now(UTC)
        if session.bind and session.bind.dialect.name == "sqlite"
        else func.clock_timestamp()
    )


def lease_value(session: AsyncSession, seconds: int) -> Any:
    return now_value(session) + timedelta(seconds=seconds)


async def append_event(
    session: AsyncSession, experiment: Experiment, kind: str, payload: dict[str, Any]
) -> None:
    # Caller holds the experiment row lock. Sequence and state commit together.
    session.add(
        ExperimentEvent(
            id=str(uuid.uuid4()),
            experiment_id=experiment.id,
            sequence=experiment.next_sequence,
            type=kind,
            payload=payload,
        )
    )
    experiment.next_sequence += 1


@dataclass(frozen=True)
class Claim:
    task_id: str
    attempt_id: str
    experiment_id: str
    worker_id: str
    spec: dict[str, Any]


async def claim_next(
    sm: async_sessionmaker[AsyncSession], worker_id: str, lease_seconds: int = 45
) -> Claim | None:
    async with sm() as session:
        task = await session.scalar(
            select(ExperimentTask)
            .join(Experiment, Experiment.id == ExperimentTask.experiment_id)
            .where(
                Experiment.status.in_(("queued", "running", "cancelled")),
                or_(
                    ExperimentTask.status == "queued",
                    (ExperimentTask.status == "running")
                    & (ExperimentTask.lease_expires_at < now_value(session)),
                ),
            )
            .order_by(ExperimentTask.created_at, ExperimentTask.id)
            .with_for_update(skip_locked=True, of=ExperimentTask)
            .limit(1)
        )
        if task is None:
            return None
        experiment = await session.scalar(
            select(Experiment).where(Experiment.id == task.experiment_id).with_for_update()
        )
        assert experiment is not None
        if experiment.cancel_requested:
            task.status = "cancelled"
            task.lease_owner = None
            task.lease_expires_at = None
            if experiment.status == "cancelled":
                # Queued cancellation is final at the API. Older rows may still need
                # their terminal event, but polling must never rewrite their outcome.
                last_event = await session.scalar(
                    select(ExperimentEvent.type).where(
                        ExperimentEvent.experiment_id == experiment.id,
                        ExperimentEvent.sequence == experiment.next_sequence - 1,
                    )
                )
                if last_event == "cancel.requested":
                    await append_event(
                        session, experiment, "experiment.finished", {"status": "cancelled"}
                    )
                await session.commit()
                return None
            experiment.status = "cancelled"
            experiment.stage = "cancelled"
            experiment.finished_at = now_value(session)
            experiment.outcome = {
                **experiment.outcome,
                "kind": "insufficient_evidence",
                "execution_complete": False,
                "objective_status": "incomplete",
                "interpretation": (
                    "Calculation was cancelled; any partial evidence remains available."
                ),
            }
            if task.active_attempt_id:
                old = await session.get(ExperimentAttempt, task.active_attempt_id)
                if old and old.status == "running":
                    old.status = "cancelled"
                    old.finished_at = now_value(session)
            await append_event(session, experiment, "experiment.finished", {"status": "cancelled"})
            await session.commit()
            return None
        previous = task.active_attempt_id
        if previous:
            old = await session.get(ExperimentAttempt, previous)
            if old and old.status == "running":
                old.status = "abandoned"
                old.error = "Worker lease expired; a new attempt reclaimed the work."
                old.finished_at = now_value(session)
        attempt_id = str(uuid.uuid4())
        task.attempt_number += 1
        task.active_attempt_id = attempt_id
        task.lease_owner = worker_id
        task.lease_expires_at = lease_value(session, lease_seconds)
        task.status = "running"
        experiment.status = "running"
        experiment.stage = "preparing"
        experiment.error = None
        experiment.finished_at = None
        # New attempts cannot present old candidate counts as fresh results.
        # Prior evidence remains queryable under its explicit attempt identity.
        experiment.counts = {
            "active_attempt_id": attempt_id,
            "previous_attempt_id": previous,
            "proposals": 0,
            "evaluated": 0,
            "poses": 0,
            "review_ready": 0,
            "objective_hits": 0,
        }
        experiment.outcome = {"kind": "pending", "execution_complete": False}
        if experiment.started_at is None:
            experiment.started_at = now_value(session)
        session.add(
            ExperimentAttempt(
                id=attempt_id,
                task_id=task.id,
                number=task.attempt_number,
                worker_id=worker_id,
                status="running",
            )
        )
        await append_event(
            session,
            experiment,
            "attempt.started",
            {
                "attempt_id": attempt_id,
                "number": task.attempt_number,
                "reclaimed": previous is not None,
            },
        )
        claim = Claim(task.id, attempt_id, experiment.id, worker_id, dict(experiment.spec))
        await session.commit()
        return claim


async def owned_task(session: AsyncSession, claim: Claim) -> ExperimentTask | None:
    row: ExperimentTask | None = await session.scalar(
        select(ExperimentTask)
        .where(
            ExperimentTask.id == claim.task_id,
            ExperimentTask.active_attempt_id == claim.attempt_id,
            ExperimentTask.lease_owner == claim.worker_id,
            ExperimentTask.status == "running",
        )
        .with_for_update()
    )
    if row is not None:
        # Check after acquiring the lock. A lock wait must not extend ownership
        # using a timestamp captured before the wait or at transaction start.
        clock = now_value(session)
        now = clock if isinstance(clock, datetime) else await session.scalar(select(clock))
        assert now is not None
        expiry = row.lease_expires_at
        if expiry is None:
            return None
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        if expiry <= now:
            return None
    return row


async def renew(
    sm: async_sessionmaker[AsyncSession], claim: Claim, lease_seconds: int = 45
) -> tuple[bool, bool]:
    async with sm() as session:
        task = await owned_task(session, claim)
        if task is None:
            return False, False
        experiment = await session.get(Experiment, claim.experiment_id)
        assert experiment is not None
        task.lease_expires_at = lease_value(session, lease_seconds)
        cancel = experiment.cancel_requested
        await session.commit()
        return True, cancel


async def record_progress(
    sm: async_sessionmaker[AsyncSession], claim: Claim, payload: dict[str, Any]
) -> bool:
    async with sm() as session:
        if await owned_task(session, claim) is None:
            return False
        experiment = await session.scalar(
            select(Experiment).where(Experiment.id == claim.experiment_id).with_for_update()
        )
        assert experiment is not None
        stage = payload.get("stage")
        if isinstance(stage, str):
            experiment.stage = stage[:80]
        await append_event(session, experiment, str(payload.get("type", "progress"))[:80], payload)
        await session.commit()
        return True


async def finish(
    sm: async_sessionmaker[AsyncSession], claim: Claim, status: str, error: str | None = None
) -> bool:
    if status not in {"completed", "completed_with_errors", "failed", "cancelled"}:
        raise ValueError("finish requires a terminal experiment status")
    async with sm() as session:
        task = await owned_task(session, claim)
        if task is None:
            return False
        experiment = await session.scalar(
            select(Experiment).where(Experiment.id == claim.experiment_id).with_for_update()
        )
        assert experiment is not None
        if experiment.cancel_requested:
            status = "cancelled"
        task.status = status
        task.lease_expires_at = None
        task.lease_owner = None
        experiment.status = status
        experiment.stage = status
        experiment.error = error
        experiment.finished_at = now_value(session)
        if status in ("cancelled", "failed"):
            experiment.outcome = {
                **experiment.outcome,
                "kind": "insufficient_evidence",
                "execution_complete": False,
                "objective_status": "incomplete",
                "interpretation": (
                    "Calculation was cancelled; any partial evidence remains available."
                    if status == "cancelled"
                    else "Calculation failed; any partial evidence remains available."
                ),
            }
        else:
            experiment.outcome = {**experiment.outcome, "execution_complete": True}
        attempt = await session.get(ExperimentAttempt, claim.attempt_id)
        assert attempt is not None
        attempt.status = status
        attempt.error = error
        attempt.finished_at = now_value(session)
        attempt.result_summary = {
            **(attempt.result_summary or {}),
            "outcome": experiment.outcome,
        }
        await append_event(
            session,
            experiment,
            "experiment.finished",
            {
                "status": status,
                "outcome": experiment.outcome,
                "error": error,
            },
        )
        await session.commit()
        return True


async def heartbeat(
    sm: async_sessionmaker[AsyncSession], worker_id: str, health: dict[str, Any] | None = None
) -> None:
    async with sm() as session:
        row = await session.get(ExperimentWorkerHeartbeat, worker_id)
        if row is None:
            session.add(
                ExperimentWorkerHeartbeat(
                    worker_id=worker_id, last_seen_at=now_value(session), health=health
                )
            )
        else:
            row.last_seen_at = now_value(session)
            if health is not None:
                row.health = health
        await session.commit()
