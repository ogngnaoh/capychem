"""Experiment submission, immutable input resolution and scientific report ingestion."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .artifacts import publish_file
from .models import (
    Artifact,
    Experiment,
    ExperimentAttempt,
    ExperimentCandidate,
    ExperimentTask,
    Pose,
    PoseEvaluation,
    PreparedMolecule,
    TargetPreparation,
)
from .queue import Claim, append_event, owned_task
from .schemas import CreateExperiment
from .science_config import load_preset, protocol_descriptor, reference_data_dir


class ConflictError(ValueError):
    pass


class ConfigurationError(ValueError):
    pass


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def reference_manifest(target_preparation_id: str = "cdk2_1h1p") -> dict[str, Any]:
    base = reference_data_dir(target_preparation_id)
    path = base / "manifest.json"
    if not path.is_file():
        raise ConfigurationError("CDK2 reference inputs are not installed. See setup readiness.")
    try:
        manifest = load_preset(target_preparation_id, verify=True)
    except (OSError, ValueError, KeyError) as exc:
        raise ConfigurationError(f"CDK2 reference inputs failed validation: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ConfigurationError("Reference manifest must be a JSON object.")
    manifest["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


def experiment_out(row: Experiment) -> dict[str, Any]:
    return {
        "id": row.id,
        "label": row.label,
        "status": row.status,
        "stage": row.stage,
        "outcome": row.outcome,
        "spec": row.spec,
        "spec_hash": row.spec_hash,
        "parent_experiment_id": row.parent_experiment_id,
        "counts": row.counts,
        "error": row.error,
        "cancel_requested": row.cancel_requested,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "latest_sequence": row.next_sequence - 1,
    }


def request_intent(request: CreateExperiment) -> dict[str, Any]:
    # Keep existing idempotency hashes stable when this additive metadata is absent.
    value = request.model_dump(mode="json")
    if not value["candidate_origins"]:
        value.pop("candidate_origins")
    return value


async def submit(
    sm: async_sessionmaker[AsyncSession], request: CreateExperiment, idempotency_key: str | None
) -> tuple[Experiment, bool]:
    try:
        return await _submit_once(sm, request, idempotency_key)
    except IntegrityError:
        # The unique-key race can occur at an intermediate flush, before commit.
        # Resolve it only after the losing transaction has rolled back/closed.
        if idempotency_key:
            async with sm() as session:
                existing = await session.scalar(
                    select(Experiment).where(Experiment.idempotency_key == idempotency_key)
                )
                if existing:
                    if existing.request_hash != canonical_hash(request_intent(request)):
                        raise ConflictError(
                            "This idempotency key belongs to a different experiment request."
                        ) from None
                    return existing, False
        raise


async def _submit_once(
    sm: async_sessionmaker[AsyncSession], request: CreateExperiment, idempotency_key: str | None
) -> tuple[Experiment, bool]:
    async with sm() as session:
        row, created = await create_in_session(session, request, idempotency_key)
        if created:
            await session.commit()
            await session.refresh(row)
        return row, created


async def validate_candidate_origins(session: AsyncSession, request: CreateExperiment) -> None:
    for origin in request.candidate_origins:
        candidate = await session.get(ExperimentCandidate, origin.candidate_id)
        if candidate is None or candidate.experiment_id != origin.experiment_id:
            raise ValueError("Candidate origin does not belong to its declared experiment.")
        assert request.candidate_source.kind == "supplied"
        supplied = request.candidate_source.candidates[origin.candidate_index]
        accepted: set[str | None]
        if origin.pose_id:
            pose = await session.get(Pose, origin.pose_id)
            if pose is None or pose.candidate_id != candidate.id:
                raise ValueError("Source pose does not belong to its declared candidate.")
            prepared = await session.get(PreparedMolecule, pose.prepared_molecule_id)
            accepted = {prepared.smiles} if prepared else set()
        else:
            accepted = {
                candidate.proposal_smiles,
                candidate.canonical_smiles,
                candidate.record.get("normalized_smiles"),
            }
        if supplied.smiles not in accepted:
            raise ValueError("Supplied SMILES differs from the declared source candidate or pose.")


async def create_in_session(
    session: AsyncSession,
    request: CreateExperiment,
    idempotency_key: str | None,
    *,
    frozen_protocol: dict[str, Any] | None = None,
) -> tuple[Experiment, bool]:
    """Create ordinary experiment rows inside the caller's transaction."""
    intent = request_intent(request)
    request_hash = canonical_hash(intent)
    if idempotency_key:
        existing = await session.scalar(
            select(Experiment).where(Experiment.idempotency_key == idempotency_key)
        )
        if existing:
            if existing.request_hash != request_hash:
                raise ConflictError(
                    "This idempotency key belongs to a different experiment request."
                )
            return existing, False
    if request.parent_experiment_id and not await session.get(
        Experiment, request.parent_experiment_id
    ):
        raise ValueError("The parent experiment does not exist.")
    await validate_candidate_origins(session, request)
    manifest = reference_manifest(request.target_preparation_id)
    target = await session.get(TargetPreparation, request.target_preparation_id)
    if target is None:
        # A fixed registered preset is shared by simultaneous submissions.
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        statement = (
            pg_insert(TargetPreparation)
            if session.bind and session.bind.dialect.name == "postgresql"
            else sqlite_insert(TargetPreparation)
        )
        await session.execute(
            statement.values(
                id=request.target_preparation_id,
                name=str(manifest.get("label", manifest.get("name", manifest["id"]))),
                manifest=manifest,
            ).on_conflict_do_nothing(index_elements=["id"])
        )
        target = await session.get(TargetPreparation, request.target_preparation_id)
    if target and target.manifest != manifest:
        raise ConflictError(
            "The registered target preparation changed. Register a new preparation version."
        )
    resolved = {
        **intent,
        "resolved_protocol": frozen_protocol
        or {
            **protocol_descriptor(request.protocol),
            "execution_contract_version": 2,
            # Admission time is not a hard deadline: allow the admitted
            # candidate's bounded Vina attempts plus generation/setup time.
            "wall_time_limit_seconds": min(
                7200,
                max(
                    300,
                    request.limits.evaluation_admission_seconds
                    + 120 * request.limits.embedding_attempts_per_candidate
                    + 180,
                ),
            ),
            "target_manifest_sha256": manifest["manifest_sha256"],
            "frame": manifest["coordinate_frame"],
        },
    }
    eid = str(uuid.uuid4())
    row = Experiment(
        id=eid,
        label=request.label,
        target_preparation_id=request.target_preparation_id,
        parent_experiment_id=request.parent_experiment_id,
        spec=resolved,
        spec_hash=canonical_hash(resolved),
        request_hash=request_hash,
        idempotency_key=idempotency_key,
        status="queued",
        stage="queued",
        counts={},
        outcome={},
        next_sequence=1,
        cancel_requested=False,
    )
    session.add(row)
    await session.flush()
    session.add(
        ExperimentTask(id=str(uuid.uuid4()), experiment_id=eid, status="queued", attempt_number=0)
    )
    await append_event(session, row, "experiment.queued", {"spec_hash": row.spec_hash})
    return row, True


def stable_id(experiment_id: str, kind: str, source: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"capychem/{experiment_id}/{kind}/{source}"))


async def publish_diagnostics(
    sm: async_sessionmaker[AsyncSession], claim: Claim, directory: Path
) -> bool:
    """Keep input and process logs even if science failed before writing a report."""
    artifacts = [
        await asyncio.to_thread(
            publish_file, directory, name, claim.experiment_id, claim.attempt_id
        )
        for name in ("input.json", "stderr.log", "progress.jsonl")
        if (directory / name).is_file()
    ]
    async with sm() as session:
        if await owned_task(session, claim) is None:
            return False
        for value in artifacts:
            if await session.get(Artifact, value["id"]) is None:
                session.add(Artifact(**value))
        await session.commit()
        return True


async def ingest_report(
    sm: async_sessionmaker[AsyncSession],
    claim: Claim,
    base: Path,
    report: dict[str, Any],
    final: bool = False,
) -> bool:
    """Copy immutable files first, then attach records under the attempt fence.

    A lost attempt may leave unreferenced content-addressed files, but cannot
    publish them or replace another attempt's evidence. No DB lock spans file I/O.
    """
    async with sm() as session:
        if await owned_task(session, claim) is None:
            return False
    if report.get("schema_version") != 1 or report.get("kind") != "live_computation":
        raise ValueError("Report has an unsupported identity or schema")
    if report.get("target", {}).get("id") != claim.spec["target_preparation_id"]:
        raise ValueError("Report target does not match the frozen experiment")
    if report.get("target", {}).get("frame") != claim.spec["resolved_protocol"]["frame"]:
        raise ValueError("Report coordinate frame does not match the frozen preparation")
    if report.get("protocol_manifest", {}).get("id") != claim.spec["protocol"]:
        raise ValueError("Report protocol does not match the frozen experiment")
    if report.get("request_spec") != claim.spec:
        raise ValueError("Report request does not match the frozen experiment")
    provenance = report.get("provenance", {})
    if provenance.get("request_spec_sha256") != canonical_hash(claim.spec):
        raise ValueError("Report request hash does not match the frozen experiment")
    if provenance.get("engine_fingerprint") != claim.spec["resolved_protocol"].get(
        "engine_fingerprint"
    ):
        raise ValueError("Report engine does not match the frozen experiment")
    protocol_hash = provenance.get("protocol_sha256")
    if not isinstance(protocol_hash, str) or len(protocol_hash) != 64:
        raise ValueError("Report must identify the actual executed protocol hash")
    record_ids = [r.get("id") for r in report.get("records", [])]
    if any(not isinstance(r, str) or not r for r in record_ids) or len(set(record_ids)) != len(
        record_ids
    ):
        raise ValueError("Report proposal identities must be unique nonempty strings")
    files: dict[str, dict[str, Any]] = {}
    paths: set[str] = {"inputs/request.json", "inputs/protocol.json"}
    if json.loads((base / "inputs/request.json").read_text()) != claim.spec:
        raise ValueError("Saved request artifact does not match the frozen experiment")
    if json.loads((base / "inputs/protocol.json").read_text()) != report["protocol_manifest"]:
        raise ValueError("Saved protocol artifact does not match reported evidence")
    parent = report.get("parent", {})
    for key in ("observed_sdf", "view_json"):
        if parent.get(key):
            paths.add(parent[key])
    target = report.get("target", {})
    for key in ("receptor_pdb", "receptor_pdbqt"):
        if target.get(key):
            paths.add(target[key])
    for record in report.get("records", []):
        for pose in record.get("poses", []):
            for key in ("sdf", "view_json"):
                if pose.get(key):
                    paths.add(pose[key])
    if final:
        paths.update(item["path"] for item in report.get("artifacts", []) if item.get("path"))
        paths.add("report.json")
        if (base / "stderr.log").is_file():
            paths.add("stderr.log")
        if (base / "progress.jsonl").is_file():
            paths.add("progress.jsonl")
    manifest = {item["path"]: item for item in report.get("artifacts", [])}
    if len(manifest) != len(report.get("artifacts", [])):
        raise ValueError("Scientific artifact paths must be unique")
    for relative in paths:
        files[relative] = await asyncio.to_thread(
            publish_file, base, relative, claim.experiment_id, claim.attempt_id
        )
        expected = manifest.get(relative)
        if expected and (
            files[relative]["sha256"] != expected.get("sha256")
            or files[relative]["size_bytes"] != expected.get("bytes")
        ):
            raise ValueError(f"Artifact disagrees with the scientific report: {relative}")
    if files["inputs/protocol.json"]["sha256"] != protocol_hash:
        raise ValueError("Reported protocol hash disagrees with the exact protocol artifact")
    async with sm() as session:
        if await owned_task(session, claim) is None:
            return False
        experiment = await session.scalar(
            select(Experiment).where(Experiment.id == claim.experiment_id).with_for_update()
        )
        assert experiment is not None
        for value in files.values():
            if await session.get(Artifact, value["id"]) is None:
                session.add(Artifact(**value))
        await session.flush()
        for ordinal, record in enumerate(report.get("records", [])):
            source_id = str(record.get("id", ordinal))
            candidate_id = stable_id(experiment.id, "candidate", source_id)
            candidate = await session.get(ExperimentCandidate, candidate_id)
            # Do not rewrite successful evidence from a prior attempt when reclaiming.
            # Reclaimed pipeline re-evaluates, and atomically replaces only its own
            # candidate projection; historical files/attempts remain retained.
            if candidate and candidate.attempt_id != claim.attempt_id:
                # Different attempts must not reuse immutable pose/state IDs.
                candidate_id = stable_id(
                    experiment.id, "candidate", f"{claim.attempt_id}/{source_id}"
                )
                candidate = await session.get(ExperimentCandidate, candidate_id)
                source_id = f"{claim.attempt_id[:8]}/{source_id}"
            if candidate is None:
                candidate = ExperimentCandidate(
                    id=candidate_id,
                    experiment_id=experiment.id,
                    attempt_id=claim.attempt_id,
                    source_id=source_id,
                    ordinal=ordinal,
                    name=str(record.get("name", source_id)),
                    proposal_smiles=str(record.get("proposal_smiles", record.get("smiles", ""))),
                    canonical_smiles=record.get("canonical_smiles"),
                    status=str(record.get("status", "needs_review")),
                    record=record,
                )
                session.add(candidate)
                await session.flush()
            else:
                if candidate.proposal_smiles != str(
                    record.get("proposal_smiles", "")
                ) or candidate.canonical_smiles != record.get("canonical_smiles"):
                    raise ValueError("A proposal identity changed during this attempt")
                old_pose_ids = {p["id"] for p in candidate.record.get("poses", [])}
                if not old_pose_ids <= {p["id"] for p in record.get("poses", [])}:
                    raise ValueError("A report cannot remove previously published poses")
                candidate.status = str(record.get("status", "needs_review"))
                candidate.record = record
            state_ids: dict[str, str] = {}
            states = record.get("prepared_states", [])
            if len({s["id"] for s in states}) != len(states):
                raise ValueError("Prepared-state IDs must be unique within a proposal")
            poses = record.get("poses", [])
            if len({p["id"] for p in poses}) != len(poses):
                raise ValueError("Pose IDs must be unique within a proposal")
            selected_pose = record.get("selected_pose_id")
            if selected_pose is not None and selected_pose not in {p["id"] for p in poses}:
                raise ValueError("Selected pose must belong to its proposal")
            for state in states:
                sid = str(state["id"])
                prepared_id = stable_id(candidate_id, "prepared", sid)
                state_ids[sid] = prepared_id
                existing_state = await session.get(PreparedMolecule, prepared_id)
                if existing_state is not None and existing_state.preparation != state:
                    raise ValueError("A prepared molecular identity changed during this attempt")
                if existing_state is None:
                    session.add(
                        PreparedMolecule(
                            id=prepared_id,
                            candidate_id=candidate_id,
                            source_id=sid,
                            smiles=str(state["smiles"]),
                            preparation=state,
                        )
                    )
            await session.flush()
            for pose in record.get("poses", []):
                sid = str(pose.get("prepared_state_id", "default"))
                if sid not in state_ids:
                    raise ValueError("Pose must reference a reported prepared molecular state")
                reported_state = next(s for s in states if str(s["id"]) == sid)
                if pose.get("prepared_smiles") != reported_state["smiles"]:
                    raise ValueError("Pose molecular identity disagrees with its prepared state")
                pose_id = stable_id(candidate_id, "pose", str(pose["id"]))
                existing_pose = await session.get(Pose, pose_id)
                evidence = {k: v for k, v in pose.items() if k not in ("sdf", "view_json")}
                if existing_pose is not None:
                    existing_evaluation = await session.scalar(
                        select(PoseEvaluation).where(PoseEvaluation.pose_id == pose_id)
                    )
                    if (
                        existing_pose.prepared_molecule_id != state_ids[sid]
                        or existing_pose.sdf_artifact_id != files[pose["sdf"]]["id"]
                        or existing_pose.view_artifact_id != files[pose["view_json"]]["id"]
                        or existing_evaluation is None
                        or existing_evaluation.evidence != evidence
                        or existing_evaluation.protocol_hash != protocol_hash
                    ):
                        raise ValueError("Published pose coordinates or evidence are immutable")
                if existing_pose is None:
                    session.add(
                        Pose(
                            id=pose_id,
                            candidate_id=candidate_id,
                            prepared_molecule_id=state_ids[sid],
                            target_preparation_id=experiment.target_preparation_id,
                            source_id=str(pose["id"]),
                            sdf_artifact_id=files[pose["sdf"]]["id"],
                            view_artifact_id=files[pose["view_json"]]["id"],
                            origin="predicted",
                            coordinate_frame=str(target["frame"]["id"]),
                        )
                    )
                    await session.flush()
                    session.add(
                        PoseEvaluation(
                            id=str(uuid.uuid4()),
                            pose_id=pose_id,
                            protocol_hash=protocol_hash,
                            evidence=evidence,
                        )
                    )
                if str(pose["id"]) == str(record.get("selected_pose_id")):
                    candidate.selected_pose_id = pose_id
        records = report.get("records", [])
        ready = sum(r.get("status") == "ready_for_review" for r in records)
        hits = sum(
            any(p.get("review_ready") and p.get("asp86_contact") for p in r.get("poses", []))
            for r in records
        )
        counts = {
            "proposals": len(report.get("raw_proposals", records)),
            "pending": max(0, len(report.get("raw_proposals", records)) - len(records)),
            "review_ready": ready,
            "objective_hits": hits,
            "evaluated": sum(
                bool(r.get("evaluated") or r.get("poses") or r.get("pose_errors")) for r in records
            ),
            "poses": sum(len(r.get("poses", [])) for r in records),
            "pose_errors": sum(len(r.get("pose_errors", [])) for r in records),
            "embedding_errors": sum(
                a.get("status") == "failed"
                for r in records
                for a in r.get("embedding_attempts", [])
            ),
            "excluded": sum(
                r.get("status") in ("outside_constraints", "invalid", "duplicate") for r in records
            ),
            "deferred": sum(r.get("status") == "deferred_budget" for r in records),
        }
        parent_refs = {
            key: files[value]["id"]
            for key, value in parent.items()
            if key in ("view_json", "observed_sdf") and value in files
        }
        experiment.counts = {
            **counts,
            "parent_artifacts": parent_refs,
            "active_attempt_id": claim.attempt_id,
        }
        experiment.outcome = {
            "review_candidates": ready,
            "objective_hits": hits,
            "interpretation": (
                "Calculation is in progress; current evidence is partial."
                if report.get("status") != "complete"
                else "No eligible pose evidence was produced; the objective was not assessed."
                if not ready
                else (
                    "Candidates meet the detected contact hypothesis; "
                    "binding improvement is unproven."
                )
                if hits
                else "No candidate met the detected Asp86-contact hypothesis."
            ),
            "kind": "pending"
            if report.get("status") != "complete"
            else "review_candidates"
            if ready
            else "no_eligible_candidates",
            "objective_status": "pending"
            if report.get("status") != "complete"
            else "not_assessed"
            if not ready
            else "detected"
            if hits
            else "not_detected",
            "limitations": report.get("limitations", []),
            "execution_complete": False,
        }
        attempt = await session.get(ExperimentAttempt, claim.attempt_id)
        assert attempt is not None
        attempt.result_summary = {
            "counts": counts,
            "parent_artifacts": parent_refs,
            "outcome": experiment.outcome,
        }
        if final:
            attempt.report_artifact_id = files["report.json"]["id"]
        await append_event(
            session, experiment, "results.updated", {"counts": counts, "final": final}
        )
        await session.commit()
        return True


def candidate_out(
    row: ExperimentCandidate, pose_rows: list[tuple[Pose, PoseEvaluation]]
) -> dict[str, Any]:
    record = row.record
    properties = record.get("properties") or {}
    unspecified_stereo = bool(record.get("unspecified_stereo")) or any(
        state.get("proposal_had_unspecified_stereo")
        for state in record.get("prepared_states", [])
    )
    stereochemistry_note = record.get("stereochemistry_note")
    if unspecified_stereo and not stereochemistry_note:
        # Derive the warning from immutable evidence, including older reports
        # that saved the stereo metadata but did not provide a display note.
        stereochemistry_note = (
            "Input stereochemistry is unspecified. Each pose shows a sampled "
            "stereoisomer; alternatives were not exhaustively sampled. "
            "Review-ready describes pose checks, not a resolved input identity."
        )
    poses = []
    selected: dict[str, Any] = {}
    for pose, evaluation in pose_rows:
        ev = evaluation.evidence
        entry = {
            "id": pose.id,
            "structureId": pose.id,
            "label": pose.source_id,
            "score": ev.get("score", ev.get("vina_score")),
            "checks": "pass" if ev.get("geometry_pass") else "fail",
            "contacts": len(ev.get("contacts", [])),
            "ringDriftA": ev.get("ring_drift_A", ev.get("purine_ring_drift_A")),
            "reviewReady": bool(ev.get("review_ready")),
            "asp86Contact": ev.get("asp86_contact"),
            "preparedMoleculeId": pose.prepared_molecule_id,
            "preparedStateId": pose.prepared_molecule_id,
            "preparedSmiles": ev.get("prepared_smiles"),
            "smiles": ev.get("prepared_smiles"),
            "hydrogenPreparation": ev.get("hydrogen_preparation"),
            "sdfUrl": f"/artifacts/{pose.sdf_artifact_id}",
            "evidence": ev,
        }
        poses.append(entry)
        if pose.id == row.selected_pose_id:
            selected = entry
    return {
        "id": row.id,
        "sourceId": row.source_id,
        "duplicateOfSourceId": record.get("duplicate_of"),
        "error": record.get("error"),
        "name": row.name,
        "description": "Live local calculation",
        "origin": "generated",
        "status": row.status,
        "structureId": row.selected_pose_id,
        "receptorId": "1H1P",
        "smiles": selected.get("smiles") or row.canonical_smiles or row.proposal_smiles,
        "proposalSmiles": row.proposal_smiles,
        "normalizedSmiles": record.get("normalized_smiles"),
        "mw": properties.get("molecular_weight", properties.get("mw")),
        "clogp": properties.get("clogp"),
        "rotors": properties.get("rotatable_bonds"),
        "formalCharge": properties.get("formal_charge"),
        "charge": properties.get("formal_charge"),
        "source": record.get("source"),
        "contacts": selected.get("contacts", 0),
        "checks": selected.get("checks", "unavailable"),
        "failures": record.get("filter_failures", []),
        "score": selected.get("score"),
        "poseCount": len(poses),
        "ringDriftA": selected.get("ringDriftA"),
        "reviewReady": selected.get("reviewReady", False),
        "asp86Contact": selected.get("asp86Contact"),
        "hydrogenPreparation": selected.get("hydrogenPreparation"),
        "partial": bool(record.get("partial")),
        "poseErrors": record.get("pose_errors", []),
        "embeddingErrors": [
            a for a in record.get("embedding_attempts", []) if a.get("status") == "failed"
        ],
        "unspecifiedStereochemistry": unspecified_stereo,
        "stereochemistryNote": stereochemistry_note,
        "selectionPolicy": "Review-ready, then Asp86 if present, then lowest Vina score",
        "poses": poses,
        "ordinal": row.ordinal,
    }
