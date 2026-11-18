"""Immutable repeated-seed studies composed of ordinary experiment jobs."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import Experiment, ExperimentStudy, StudyMember
from .routes import (
    ExperimentRoute,
    candidates_for,
    export_in_session,
    request_cancellation,
    sessions,
)
from .schemas import CreateExperiment, CreateStudy
from .service import (
    ConfigurationError,
    ConflictError,
    canonical_hash,
    create_in_session,
    experiment_out,
)

router = APIRouter(tags=["studies"], route_class=ExperimentRoute)
TERMINAL = {"completed", "completed_with_errors", "failed", "cancelled"}
SELECTION = (
    "Protocol selects review-ready poses, then detected Asp86 contact, then lowest Vina score. "
    "Saved user preferred poses do not change study counts."
)


async def create_study(
    sm: async_sessionmaker[AsyncSession], body: CreateStudy, key: str | None
) -> tuple[str, bool]:
    request_hash = canonical_hash(body.model_dump(mode="json"))

    async def existing(session: AsyncSession) -> ExperimentStudy | None:
        if key is None:
            return None
        row = await session.scalar(
            select(ExperimentStudy).where(ExperimentStudy.idempotency_key == key)
        )
        if row and row.request_hash != request_hash:
            raise ConflictError("This idempotency key belongs to a different study request.")
        return row

    try:
        async with sm() as session:
            previous = await existing(session)
            if previous:
                return previous.id, False
            study_id = str(uuid.uuid4())
            rows = []
            frozen_protocol = None
            for ordinal, seeds in enumerate(body.seed_pairs):
                intent = CreateExperiment.model_validate(
                    {
                        **body.base_spec.model_dump(),
                        "label": f"{body.label[:140]} · seed run {ordinal + 1}",
                        "seeds": seeds.model_dump(),
                    }
                )
                row, created = await create_in_session(
                    session,
                    intent,
                    f"study-{study_id}-{ordinal}",
                    frozen_protocol=frozen_protocol,
                )
                assert created
                frozen_protocol = row.spec["resolved_protocol"]
                rows.append(row)
            base_spec = {k: v for k, v in rows[0].spec.items() if k not in {"label", "seeds"}}
            pairs = [seeds.model_dump() for seeds in body.seed_pairs]
            study = ExperimentStudy(
                id=study_id,
                label=body.label,
                base_spec=base_spec,
                seed_pairs=pairs,
                spec_hash=canonical_hash({"base_spec": base_spec, "seed_pairs": pairs}),
                request_hash=request_hash,
                idempotency_key=key,
            )
            session.add(study)
            await session.flush()
            for ordinal, row in enumerate(rows):
                session.add(StudyMember(study_id=study_id, experiment_id=row.id, ordinal=ordinal))
            await session.commit()
            return study_id, True
    except IntegrityError:
        async with sm() as session:
            previous = await existing(session)
            if previous:
                return previous.id, False
        raise


async def require_study(session: AsyncSession, study_id: str) -> ExperimentStudy:
    row = await session.get(ExperimentStudy, study_id)
    if row is None:
        raise HTTPException(404, "Study not found")
    return row


async def members_for(
    session: AsyncSession, study_id: str, *, lock: bool = False
) -> list[tuple[StudyMember, Experiment]]:
    statement = (
        select(StudyMember, Experiment)
        .join(Experiment, StudyMember.experiment_id == Experiment.id)
        .where(StudyMember.study_id == study_id)
    )
    if lock:
        # A common order prevents group export/cancel from deadlocking each other.
        statement = statement.order_by(Experiment.id).with_for_update(of=Experiment)
    rows = list((await session.execute(statement)).tuples())
    return sorted(rows, key=lambda pair: pair[0].ordinal)


def study_status(rows: list[tuple[StudyMember, Experiment]]) -> tuple[str, dict[str, int]]:
    counts = dict(Counter(row.status for _, row in rows))
    if any(row.status == "running" for _, row in rows):
        status = "running"
    elif any(row.status == "queued" for _, row in rows):
        status = "queued"
    elif counts.get("cancelled") == len(rows):
        status = "cancelled"
    elif counts.get("failed") == len(rows):
        status = "failed"
    elif counts.get("completed") == len(rows):
        status = "completed"
    else:
        status = "completed_with_errors"
    return status, {
        "planned": len(rows),
        "finished": sum(row.status in TERMINAL for _, row in rows),
        **counts,
    }


async def study_out(
    session: AsyncSession,
    study: ExperimentStudy,
    *,
    include_candidates: bool = True,
    rows: list[tuple[StudyMember, Experiment]] | None = None,
) -> dict[str, Any]:
    if rows is None:
        rows = await members_for(session, study.id)
    status, counts = study_status(rows)
    result = {
        "schema_version": 1,
        "id": study.id,
        "label": study.label,
        "status": status,
        "base_spec": study.base_spec,
        "seed_pairs": study.seed_pairs,
        "spec_hash": study.spec_hash,
        "created_at": study.created_at,
        "counts": counts,
        "selection_policy": SELECTION,
        "frequency_interpretation": (
            "Observed counts across declared seed runs, not probabilities, "
            "affinity estimates, or independent biological evidence."
        ),
        "members": [
            {
                "ordinal": member.ordinal,
                "seeds": row.spec["seeds"],
                "experiment": experiment_out(row),
            }
            for member, row in rows
        ],
    }
    if not include_candidates:
        return result
    inputs = study.base_spec["candidate_source"]["candidates"]
    aggregates = [
        {
            "candidate_index": i,
            "name": item["name"],
            "smiles": item["smiles"],
            "planned_runs": len(rows),
            "completed_runs": 0,
            "observed_runs": 0,
            "review_ready_runs": 0,
            "contact_hit_runs": 0,
            "observations": [],
        }
        for i, item in enumerate(inputs)
    ]
    for member, experiment in rows:
        candidates = {c["ordinal"]: c for c in await candidates_for(session, experiment)}
        for aggregate in aggregates:
            candidate = candidates.get(aggregate["candidate_index"])
            pose = (
                next(
                    (
                        p
                        for p in (candidate or {}).get("poses", [])
                        if p["id"] == candidate.get("structureId")
                    ),
                    None,
                )
                if candidate
                else None
            )
            observed = bool(pose and isinstance(pose.get("asp86Contact"), bool))
            eligible = bool(pose and pose["reviewReady"])
            hit = bool(pose and eligible and pose["asp86Contact"])
            aggregate["completed_runs"] += experiment.status in {
                "completed",
                "completed_with_errors",
            }
            aggregate["observed_runs"] += observed
            aggregate["review_ready_runs"] += eligible
            aggregate["contact_hit_runs"] += hit
            aggregate["observations"].append(
                {
                    "run_ordinal": member.ordinal,
                    "seeds": experiment.spec["seeds"],
                    "experiment_id": experiment.id,
                    "experiment_status": experiment.status,
                    "execution_complete": experiment.status
                    in {"completed", "completed_with_errors"},
                    "attempt_id": experiment.counts.get("active_attempt_id"),
                    "candidate_id": candidate["id"] if candidate else None,
                    "status": candidate["status"] if candidate else "not_processed",
                    "normalized_smiles": candidate.get("normalizedSmiles") if candidate else None,
                    "duplicate_of_candidate_id": candidate.get("duplicateOfCandidateId")
                    if candidate
                    else None,
                    "selected_pose_id": pose["id"] if pose else None,
                    "prepared_state_id": pose["preparedStateId"] if pose else None,
                    "prepared_smiles": pose["preparedSmiles"] if pose else None,
                    "unspecified_stereochemistry": candidate.get("unspecifiedStereochemistry")
                    if candidate
                    else None,
                    "stereochemistry_note": candidate.get("stereochemistryNote")
                    if candidate
                    else None,
                    "hydrogen_preparation": pose.get("hydrogenPreparation") if pose else None,
                    "score": pose["score"] if pose else None,
                    "review_ready": eligible if pose else None,
                    "asp86_contact": pose["asp86Contact"] if pose else None,
                    "asp86_contacts": [
                        contact
                        for contact in pose["evidence"].get("contacts", [])
                        if contact.get("residue") == "ASP86.A"
                    ]
                    if pose and observed
                    else None,
                    "sdf_url": pose["sdfUrl"] if pose else None,
                    "error": candidate.get("error") if candidate else experiment.error,
                    "filter_failures": candidate.get("failures", []) if candidate else [],
                }
            )
    result["candidates"] = aggregates
    return result


@router.post("/studies", status_code=201)
async def post_study(
    body: CreateStudy,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
        raise HTTPException(422, "Idempotency-Key must contain 1–128 characters.")
    try:
        study_id, created = await create_study(sessions(request), body, idempotency_key)
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not created:
        response.status_code = 200
    async with sessions(request)() as session:
        return await study_out(session, await require_study(session, study_id))


@router.get("/studies")
async def list_studies(
    request: Request, limit: int = Query(default=50, ge=1, le=100), cursor: str | None = None
) -> dict[str, Any]:
    async with sessions(request)() as session:
        sqlite = session.bind and session.bind.dialect.name == "sqlite"
        sort_time = (
            func.julianday(ExperimentStudy.created_at) if sqlite else ExperimentStudy.created_at
        )
        statement = select(ExperimentStudy)
        if cursor:
            try:
                anchor_id = str(uuid.UUID(cursor))
            except ValueError as exc:
                raise HTTPException(422, "Invalid study cursor") from exc
            anchor = await session.get(ExperimentStudy, anchor_id)
            if anchor is None:
                raise HTTPException(422, "Study cursor is unavailable; restart the list.")
            marker = func.julianday(anchor.created_at) if sqlite else anchor.created_at
            statement = statement.where(
                or_(sort_time < marker, (sort_time == marker) & (ExperimentStudy.id < anchor.id))
            )
        rows = (
            await session.scalars(
                statement.order_by(sort_time.desc(), ExperimentStudy.id.desc()).limit(limit + 1)
            )
        ).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        return {
            "items": [await study_out(session, row, include_candidates=False) for row in rows],
            "next_cursor": rows[-1].id if has_more else None,
            "has_more": has_more,
        }


@router.get("/studies/{study_id}")
async def get_study(study_id: str, request: Request) -> dict[str, Any]:
    async with sessions(request)() as session:
        study = await require_study(session, study_id)
        return await study_out(session, study, rows=await members_for(session, study_id, lock=True))


@router.post("/studies/{study_id}/cancel")
async def cancel_study(study_id: str, request: Request) -> dict[str, Any]:
    async with sessions(request)() as session:
        study = await require_study(session, study_id)
        rows = await members_for(session, study_id, lock=True)
        for _, row in rows:
            await request_cancellation(session, row)
        await session.commit()
        # Re-read the derived result after committing all cancellation requests.
        return await study_out(session, study)


@router.get("/studies/{study_id}/export")
async def export_study(study_id: str, request: Request, response: Response) -> dict[str, Any]:
    async with sessions(request)() as session:
        study = await require_study(session, study_id)
        rows = await members_for(session, study_id, lock=True)
        response.headers["Content-Disposition"] = (
            f'attachment; filename="capychem-study-{study_id}.json"'
        )
        return {
            "schema_version": 1,
            "kind": "repeated_seed_study",
            "study": await study_out(session, study, rows=rows),
            "experiments": [await export_in_session(session, row) for _, row in rows],
        }
