"""Local single-user experiment API; chemistry is executed only by workers."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .artifacts import verified_path
from .models import (
    Artifact,
    Experiment,
    ExperimentAttempt,
    ExperimentCandidate,
    ExperimentDecision,
    ExperimentEvent,
    ExperimentTask,
    ExperimentWorkerHeartbeat,
    Pose,
    PoseEvaluation,
    TargetPreparation,
)
from .queue import append_event, now_value
from .runtime import configuration_fingerprint
from .schemas import CreateExperiment, DecisionRequest
from .science_config import protocol_descriptor, supported_presets
from .service import (
    ConfigurationError,
    ConflictError,
    candidate_out,
    canonical_hash,
    experiment_out,
    reference_manifest,
    stable_id,
    submit,
)


class ExperimentRoute(APIRoute):
    """Return useful 422s even when invalid input contains JSON NaN/Infinity.

    FastAPI's default validation response includes the rejected raw input;
    encoding a non-finite float in that response otherwise raises another error.
    Field locations, messages and error types are sufficient for the client.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": [
                            {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                            for error in exc.errors()
                        ]
                    },
                )

        return handle


router = APIRouter(tags=["experiments"], route_class=ExperimentRoute)


def sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    return cast(async_sessionmaker[AsyncSession], request.app.state.sessionmaker)


async def require_experiment(session: AsyncSession, eid: str, lock: bool = False) -> Experiment:
    statement = select(Experiment).where(Experiment.id == eid)
    if lock:
        statement = statement.with_for_update()
    row = await session.scalar(statement)
    if row is None:
        raise HTTPException(404, "Experiment not found")
    return row


async def candidates_for(
    session: AsyncSession, experiment: Experiment, attempt_id: str | None = None
) -> list[dict[str, Any]]:
    query = select(ExperimentCandidate).where(ExperimentCandidate.experiment_id == experiment.id)
    active = attempt_id or experiment.counts.get("active_attempt_id")
    if active:
        query = query.where(ExperimentCandidate.attempt_id == active)
    candidates = (
        await session.scalars(query.order_by(ExperimentCandidate.ordinal, ExperimentCandidate.id))
    ).all()
    if not candidates:
        return []
    all_poses = (
        await session.execute(
            select(Pose, PoseEvaluation)
            .join(PoseEvaluation, PoseEvaluation.pose_id == Pose.id)
            .where(Pose.candidate_id.in_([c.id for c in candidates]))
        )
    ).all()
    by_candidate: dict[str, list[Any]] = {}
    for pose, evaluation in all_poses:
        by_candidate.setdefault(pose.candidate_id, []).append((pose, evaluation))
    target = await session.get(TargetPreparation, experiment.target_preparation_id)
    receptor_id = (
        target.manifest.get("receptor_pdb_id") or target.manifest.get("source", {}).get("pdb")
        if target
        else None
    )
    # Reports refer to their raw proposal IDs. Recovered candidates have a
    # namespaced source_id, so resolve through the preserved report identity
    # within the same attempt rather than comparing molecular strings.
    source_candidates = {
        (c.attempt_id, str(c.record.get("id", c.ordinal))): c.id for c in candidates
    }
    return [
        {
            **candidate_out(c, by_candidate.get(c.id, [])),
            "duplicateOfCandidateId": (
                source_candidates.get((c.attempt_id, str(c.record["duplicate_of"])))
                if c.record.get("duplicate_of") is not None
                else None
            ),
            "receptorId": receptor_id,
            "attemptId": c.attempt_id,
        }
        for c in candidates
    ]


async def require_attempt(session: AsyncSession, eid: str, attempt_id: str) -> ExperimentAttempt:
    attempt = await session.scalar(
        select(ExperimentAttempt)
        .join(ExperimentTask, ExperimentTask.id == ExperimentAttempt.task_id)
        .where(ExperimentAttempt.id == attempt_id, ExperimentTask.experiment_id == eid)
    )
    if attempt is None:
        raise HTTPException(404, "Attempt not found in this experiment")
    return attempt


@router.get("/experiments/readiness")
async def readiness(request: Request) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    result: dict[str, Any] = {}
    try:
        from .science_config import readiness as science_readiness

        result = science_readiness()
        checks.append(
            {
                "name": "science_environment",
                "ok": bool(result.get("configured")),
                "message": "; ".join(result.get("problems", []))
                or "Scientific executables and verified reference inputs are configured.",
            }
        )
    except Exception as exc:
        checks.append({"name": "science_environment", "ok": False, "message": str(exc)})
    worker: dict[str, Any] = {"last_seen_at": None, "online": False}
    runtime: dict[str, Any] = {}
    try:
        async with sessions(request)() as session:
            await session.execute(text("SELECT 1"))
            checks.append({"name": "database", "ok": True, "message": "Postgres is reachable."})
            rows = (
                await session.scalars(
                    select(ExperimentWorkerHeartbeat)
                    .order_by(ExperimentWorkerHeartbeat.last_seen_at.desc())
                    .limit(10)
                )
            ).all()
            fingerprint = configuration_fingerprint()
            matching = [
                r for r in rows if (r.health or {}).get("configuration_fingerprint") == fingerprint
            ]
            latest = next(
                (
                    r
                    for r in matching
                    if (r.health or {}).get("state") == "ready"
                    and (
                        datetime.now(UTC)
                        - (
                            r.last_seen_at.replace(tzinfo=UTC)
                            if r.last_seen_at.tzinfo is None
                            else r.last_seen_at
                        )
                    ).total_seconds()
                    < 30
                ),
                matching[0] if matching else (rows[0] if rows else None),
            )
            if latest:
                seen = latest.last_seen_at
                aware = seen.replace(tzinfo=UTC) if seen.tzinfo is None else seen
                runtime = latest.health or {}
                worker = {
                    "last_seen_at": seen,
                    "online": -5 <= (datetime.now(UTC) - aware).total_seconds() < 30
                    and runtime.get("state") != "stopped",
                    "id": latest.worker_id,
                    "health": runtime,
                }
            checks.append(
                {
                    "name": "worker",
                    "ok": worker["online"],
                    "message": "Local worker is online."
                    if worker["online"]
                    else "Start the local experiment worker to run calculations.",
                }
            )
            runtime_ok = (
                worker["online"]
                and runtime.get("state") == "ready"
                and runtime.get("configuration_fingerprint") == fingerprint
                and runtime.get("science", {}).get("ok")
            )
            checks.append(
                {
                    "name": "runtime",
                    "ok": bool(runtime_ok),
                    "message": "Worker verified the chemistry dependencies and artifact store."
                    if runtime_ok
                    else runtime.get("science", {}).get("message")
                    or (
                        "Worker runtime is unverified or its configuration changed. "
                        "The worker checks setup automatically and retries failed probes."
                    ),
                }
            )
    except Exception:
        checks.append(
            {
                "name": "database",
                "ok": False,
                "message": "Database or experiment migrations are unavailable.",
            }
        )
    return {
        "ready": bool(checks) and all(c.get("ok", False) for c in checks),
        "checks": checks,
        "worker": worker,
        "capabilities": {
            "libinvent": bool(
                worker["online"]
                and runtime.get("generator", {}).get("ok")
                and runtime.get("configuration_fingerprint") == configuration_fingerprint()
            )
        },
        "configuration": {
            key: result.get(key)
            for key in (
                "science_python",
                "vina_binary",
                "reference_data_dir",
                "libinvent_configured",
            )
        },
    }


@router.get("/experiments/presets")
async def presets() -> dict[str, Any]:
    try:
        manifests = [reference_manifest(m["id"]) for m in supported_presets()]
    except (OSError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc
    recommended = "cdk2_1h1s_nu6094_v1"
    manifests.sort(key=lambda m: m["id"] != recommended)
    items = []
    for manifest in manifests:
        candidates = [
            {"name": c["name"], "smiles": c["smiles"]}
            for c in manifest.get("reference_candidates", [])
        ]
        label = manifest.get("label", manifest.get("name", manifest["id"]))
        default = CreateExperiment.model_validate(
            {
                "label": f"{label} · known ligand review",
                "target_preparation_id": manifest["id"],
                "protocol": manifest.get("protocol", "guided_local_cdk2_v1"),
                "candidate_source": {"kind": "supplied", "candidates": candidates},
                **manifest.get("default_spec", {"constraints": {"max_clogp": 5.0}}),
            }
        ).model_dump(mode="json")
        descriptor = protocol_descriptor(default["protocol"])
        legacy = manifest["id"] == "cdk2_1h1p"
        legacy_note = (
            "Historical NU2058/1H1P comparison: this protocol missed the known "
            "NU6102–Asp86 contact. Use NU6094 para growth for the validated curated control."
        )
        items.append(
            {
                "id": manifest["id"],
                "name": f"{label} · legacy" if legacy else label,
                "description": legacy_note
                if legacy
                else manifest.get("description", "Evaluate the registered CDK2 ligand series."),
                "recommended": manifest["id"] == recommended,
                "default_spec": default,
                "reference_candidates": candidates,
                "manifest": manifest,
                "receptor_pdb_id": manifest.get("receptor_pdb_id")
                or manifest.get("source", {}).get("pdb"),
                "parent": manifest.get("parent", {"name": "NU2058", "pose_kind": "observed"}),
                "attachment": manifest["scaffold"]["attachment_atom_name"],
                "retained_heavy_atoms": manifest["scaffold"]["retained_heavy_atoms"],
                "protocol_descriptor": descriptor,
                "scope": legacy_note
                if legacy
                else manifest.get(
                    "scope",
                    descriptor.get(
                        "validation_scope", "One prepared CDK2 receptor; ligand motion is allowed."
                    ),
                ),
                "validation_scope": manifest.get("validation_scope"),
                "limitations": [
                    *manifest.get("limitations", []),
                    *([legacy_note] if legacy else []),
                ],
            }
        )
    return {"presets": items, "default_preset_id": items[0]["id"] if items else None}


@router.post("/experiments", status_code=201)
async def create_experiment(
    body: CreateExperiment,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
        raise HTTPException(422, "Idempotency-Key must contain 1–128 characters.")
    try:
        row, created = await submit(sessions(request), body, idempotency_key)
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not created:
        response.status_code = 200
    return experiment_out(row)


@router.get("/experiments")
async def list_experiments(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=1024),
    status: Literal[
        "queued", "running", "completed", "completed_with_errors", "failed", "cancelled"
    ]
    | None = None,
    q: str = Query(default="", max_length=160),
) -> dict[str, Any]:
    query_text = q.strip()
    filters = canonical_hash({"status": status, "q": query_text})
    statement = select(Experiment)
    if status:
        statement = statement.where(Experiment.status == status)
    if query_text:
        escaped = query_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(Experiment.label.ilike(f"%{escaped}%", escape="\\"))
    if cursor:
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
            if (
                not isinstance(value, dict)
                or set(value) != {"filters", "created_at", "id"}
                or any(not isinstance(item, str) for item in value.values())
            ):
                raise ValueError("Cursor fields must be strings")
            if value["filters"] != filters:
                raise ValueError("Cursor belongs to different filters")
            timestamp = datetime.fromisoformat(value["created_at"])
            if timestamp.tzinfo is None:
                raise ValueError("Cursor timestamp requires a timezone")
            cursor_id = str(UUID(value["id"]))
        except (ValueError, TypeError, KeyError, binascii.Error) as exc:
            raise HTTPException(422, "Invalid experiment list cursor or changed filters") from exc
    async with sessions(request)() as session:
        sort_time: Any = Experiment.created_at
        if session.bind and session.bind.dialect.name == "sqlite":
            # SQLite stores CURRENT_TIMESTAMP without fractional seconds but
            # binds datetimes with them. Compare normalized time values rather
            # than unequal string encodings in convenience-test databases.
            sort_time = func.julianday(Experiment.created_at)
        if cursor:
            marker: Any = timestamp
            if session.bind and session.bind.dialect.name == "sqlite":
                marker = func.julianday(timestamp)
            statement = statement.where(
                or_(sort_time < marker, (sort_time == marker) & (Experiment.id < cursor_id))
            )
        rows = (
            await session.scalars(
                statement.order_by(sort_time.desc(), Experiment.id.desc()).limit(limit + 1)
            )
        ).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_more:
            last = rows[-1]
            timestamp = last.created_at
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            next_cursor = (
                base64.urlsafe_b64encode(
                    json.dumps(
                        {"created_at": timestamp.isoformat(), "id": last.id, "filters": filters}
                    ).encode()
                )
                .decode()
                .rstrip("=")
            )
        return {
            "items": [experiment_out(row) for row in rows],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }


@router.get("/experiments/{eid}")
async def experiment_detail(eid: str, request: Request) -> dict[str, Any]:
    async with sessions(request)() as session:
        return experiment_out(await require_experiment(session, eid))


@router.get("/experiments/{eid}/candidates")
async def candidate_list(
    eid: str, request: Request, attempt_id: str | None = None
) -> dict[str, Any]:
    async with sessions(request)() as session:
        experiment = await require_experiment(session, eid)
        if attempt_id:
            await require_attempt(session, eid, attempt_id)
        return {"items": await candidates_for(session, experiment, attempt_id)}


@router.get("/experiments/{eid}/attempts")
async def experiment_attempts(eid: str, request: Request) -> dict[str, Any]:
    async with sessions(request)() as session:
        await require_experiment(session, eid)
        rows = (
            await session.scalars(
                select(ExperimentAttempt)
                .join(ExperimentTask, ExperimentTask.id == ExperimentAttempt.task_id)
                .where(ExperimentTask.experiment_id == eid)
                .order_by(ExperimentAttempt.number)
            )
        ).all()
        return {"items": [attempt_out(row) for row in rows]}


@router.get("/experiments/{eid}/events")
async def event_list(
    eid: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    async with sessions(request)() as session:
        await require_experiment(session, eid)
        rows = (
            await session.scalars(
                select(ExperimentEvent)
                .where(ExperimentEvent.experiment_id == eid, ExperimentEvent.sequence > after)
                .order_by(ExperimentEvent.sequence)
                .limit(limit)
            )
        ).all()
        return {
            "events": [
                {
                    "seq": r.sequence,
                    "type": r.type,
                    "payload": r.payload,
                    "created_at": r.created_at,
                }
                for r in rows
            ],
            "next_sequence": rows[-1].sequence if rows else after,
        }


async def request_cancellation(session: AsyncSession, row: Experiment) -> None:
    if row.status not in ("queued", "running") or row.cancel_requested:
        return
    row.cancel_requested = True
    if row.status == "queued":
        row.status = "cancelled"
        row.stage = "cancelled"
        row.finished_at = now_value(session)
        row.outcome = {
            "kind": "insufficient_evidence",
            "execution_complete": False,
            "objective_status": "not_assessed",
            "interpretation": "Calculation was cancelled before it started.",
        }
    await append_event(session, row, "cancel.requested", {"status": row.status})
    if row.status == "cancelled":
        await append_event(session, row, "experiment.finished", {"status": row.status})


@router.post("/experiments/{eid}/cancel")
async def cancel_experiment(eid: str, request: Request) -> dict[str, Any]:
    async with sessions(request)() as session:
        row = await require_experiment(session, eid, lock=True)
        await request_cancellation(session, row)
        await session.commit()
        await session.refresh(row)
        return experiment_out(row)


async def artifact_data(session: AsyncSession, artifact_id: str) -> tuple[Artifact, Any]:
    row = await session.get(Artifact, artifact_id)
    if row is None:
        raise HTTPException(404, "Artifact not found")
    try:
        path = verified_path(row.storage_key, row.sha256, row.size_bytes)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return row, path


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, request: Request) -> FileResponse:
    async with sessions(request)() as session:
        row, path = await artifact_data(session, artifact_id)
        return FileResponse(
            path,
            media_type=row.media_type,
            filename=row.name,
            headers={
                "ETag": f'"{row.sha256}"',
                "Cache-Control": "private, max-age=31536000, immutable",
            },
        )


@router.get("/experiments/{eid}/viewer")
async def viewer(
    eid: str, request: Request, pose_id: str | None = None, attempt_id: str | None = None
) -> dict[str, Any]:
    structures = []
    async with sessions(request)() as session:
        experiment = await require_experiment(session, eid)
        parent_refs = experiment.counts.get("parent_artifacts", {})
        active = attempt_id or experiment.counts.get("active_attempt_id")
        if attempt_id:
            attempt = await require_attempt(session, eid, attempt_id)
            if attempt.result_summary:
                parent_refs = attempt.result_summary.get("parent_artifacts", {})
            elif attempt_id != experiment.counts.get("active_attempt_id"):
                parent_refs = {}
        if parent_refs.get("view_json"):
            _, path = await artifact_data(session, parent_refs["view_json"])
            parent = json.loads(path.read_text())
            parent["id"] = f"{eid}:parent"
            if parent_refs.get("observed_sdf"):
                parent["sdfUrl"] = f"/artifacts/{parent_refs['observed_sdf']}"
            structures.append(parent)
        query = (
            select(Pose)
            .join(ExperimentCandidate, ExperimentCandidate.id == Pose.candidate_id)
            .where(ExperimentCandidate.experiment_id == eid)
        )
        if active:
            query = query.where(ExperimentCandidate.attempt_id == active)
        if pose_id:
            query = query.where(Pose.id == pose_id)
        poses = (await session.scalars(query.order_by(Pose.id))).all()
        if pose_id and not poses:
            raise HTTPException(404, "Pose not found in this experiment's active result set")
        for pose in poses:
            _, path = await artifact_data(session, pose.view_artifact_id)
            view = json.loads(path.read_text())
            view["id"] = pose.id
            view["sdfUrl"] = f"/artifacts/{pose.sdf_artifact_id}"
            view["sdfCoordinateFrame"] = pose.coordinate_frame
            structures.append(view)
    return {
        "structures": structures,
        "kind": "live_computation",
        "experimentId": eid,
        "attemptId": active,
        "parentStructureId": f"{eid}:parent",
    }


def decision_out(row: ExperimentDecision) -> dict[str, Any]:
    return {
        "candidate_id": row.candidate_id,
        "pinned": row.pinned,
        "notes": row.notes,
        "preferred_pose_id": row.preferred_pose_id,
        "updated_at": row.updated_at,
        "revision": row.revision,
    }


def attempt_out(row: ExperimentAttempt) -> dict[str, Any]:
    return {
        "id": row.id,
        "number": row.number,
        "status": row.status,
        "error": row.error,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "report_artifact_id": row.report_artifact_id,
        "counts": (row.result_summary or {}).get("counts", {}),
        "outcome": (row.result_summary or {}).get("outcome", {}),
    }


@router.get("/experiments/{eid}/decisions")
async def decisions(eid: str, request: Request) -> dict[str, Any]:
    async with sessions(request)() as session:
        await require_experiment(session, eid)
        rows = (
            await session.scalars(
                select(ExperimentDecision).where(ExperimentDecision.experiment_id == eid)
            )
        ).all()
        return {"items": [decision_out(row) for row in rows]}


@router.put("/experiments/{eid}/decisions/{candidate_id}")
@router.patch("/experiments/{eid}/decisions/{candidate_id}")
async def save_decision(
    eid: str,
    candidate_id: str,
    body: DecisionRequest,
    request: Request,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    expected_revision = body.expected_revision
    if if_match is not None:
        try:
            parsed = int(if_match.strip('"'))
            if parsed < 0 or (expected_revision is not None and expected_revision != parsed):
                raise ValueError("Conflicting revision preconditions")
            expected_revision = parsed
        except ValueError as exc:
            raise HTTPException(422, "If-Match must contain the decision revision integer") from exc
    partial = request.method == "PATCH"
    if partial and expected_revision is None:
        raise HTTPException(428, "PATCH requires If-Match or expected_revision")
    async with sessions(request)() as session:
        experiment = await require_experiment(session, eid, lock=True)
        candidate = await session.get(ExperimentCandidate, candidate_id)
        if candidate is None or candidate.experiment_id != eid:
            raise HTTPException(404, "Candidate not found in this experiment")
        if body.preferred_pose_id:
            pose = await session.get(Pose, body.preferred_pose_id)
            if pose is None or pose.candidate_id != candidate_id:
                raise HTTPException(422, "Preferred pose must belong to this candidate")
        did = stable_id(eid, "decision", candidate_id)
        row = await session.get(ExperimentDecision, did)
        actual_revision = row.revision if row else 0
        if expected_revision is not None and expected_revision != actual_revision:
            raise HTTPException(
                409,
                {
                    "message": "This decision changed; reload it before saving your changes.",
                    "current": jsonable_encoder(decision_out(row))
                    if row
                    else {
                        "candidate_id": candidate_id,
                        "pinned": False,
                        "notes": "",
                        "preferred_pose_id": None,
                        "updated_at": None,
                        "revision": 0,
                    },
                },
            )
        if row is None:
            row = ExperimentDecision(
                id=did,
                experiment_id=eid,
                candidate_id=candidate_id,
                pinned=False,
                notes="",
                preferred_pose_id=None,
            )
            session.add(row)
        for field in ("pinned", "notes", "preferred_pose_id"):
            if not partial or field in body.model_fields_set:
                setattr(row, field, getattr(body, field))
        row.revision = actual_revision + 1
        row.updated_at = now_value(session)
        await append_event(session, experiment, "decision.saved", {"candidate_id": candidate_id})
        await session.commit()
        await session.refresh(row)
        response.headers["ETag"] = f'"{row.revision}"'
        return decision_out(row)


@router.get("/experiments/{eid}/export")
async def export_experiment(eid: str, request: Request, response: Response) -> dict[str, Any]:
    async with sessions(request)() as session:
        # Publication and review lock the same row, so this snapshot is coherent.
        row = await require_experiment(session, eid, lock=True)
        response.headers["Content-Disposition"] = f'attachment; filename="capychem-{eid}.json"'
        return await export_in_session(session, row)


async def export_in_session(session: AsyncSession, row: Experiment) -> dict[str, Any]:
    eid = row.id
    candidates = await candidates_for(session, row)
    artifacts = (await session.scalars(select(Artifact).where(Artifact.experiment_id == eid))).all()
    decisions_rows = (
        await session.scalars(
            select(ExperimentDecision).where(ExperimentDecision.experiment_id == eid)
        )
    ).all()
    attempts = (
        await session.scalars(
            select(ExperimentAttempt)
            .join(ExperimentTask, ExperimentAttempt.task_id == ExperimentTask.id)
            .where(ExperimentTask.experiment_id == eid)
            .order_by(ExperimentAttempt.number)
        )
    ).all()
    return {
        "schema_version": 1,
        "kind": "live_computation",
        "experiment": experiment_out(row),
        "candidates": candidates,
        "decisions": [decision_out(d) for d in decisions_rows],
        "attempts": [
            {**attempt_out(a), "candidates": await candidates_for(session, row, a.id)}
            for a in attempts
        ],
        "artifacts": [
            {
                "id": a.id,
                "sha256": a.sha256,
                "name": a.name,
                "relative_path": a.relative_path,
                "media_type": a.media_type,
                "size_bytes": a.size_bytes,
                "url": f"/artifacts/{a.id}",
                "attempt_id": a.attempt_id,
            }
            for a in artifacts
        ],
    }
