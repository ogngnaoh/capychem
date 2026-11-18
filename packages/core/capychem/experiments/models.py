"""Durable experiment identities and execution state.

Scientific payloads are versioned JSON; queryable identity, ownership and lifecycle
fields stay relational. No coordinates are stored in database JSON.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from capychem.db.models import Base
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column


class TargetPreparation(Base):
    __tablename__ = "target_preparations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (Index("ix_experiment_created_id", "created_at", "id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    label: Mapped[str] = mapped_column(String(160))
    target_preparation_id: Mapped[str] = mapped_column(
        ForeignKey("target_preparations.id"), index=True
    )
    parent_experiment_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiments.id"), index=True
    )
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    spec_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(80), default="queued")
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    next_sequence: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperimentTask(Base):
    __tablename__ = "experiment_tasks"
    __table_args__ = (
        Index("ix_experiment_task_claim", "status", "lease_expires_at", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(40), default="local_pipeline")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempt_number: Mapped[int] = mapped_column(default=0)
    active_attempt_id: Mapped[str | None] = mapped_column(String(36))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExperimentAttempt(Base):
    __tablename__ = "experiment_attempts"
    __table_args__ = (UniqueConstraint("task_id", "number", name="uq_experiment_attempt_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("experiment_tasks.id"), index=True)
    number: Mapped[int]
    worker_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="running")
    error: Mapped[str | None] = mapped_column(Text)
    report_artifact_id: Mapped[str | None] = mapped_column(String(36))
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Artifact(Base):
    __tablename__ = "experiment_artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("experiment_attempts.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(256))
    name: Mapped[str] = mapped_column(String(200))
    relative_path: Mapped[str | None] = mapped_column(String(512))
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExperimentCandidate(Base):
    __tablename__ = "experiment_candidates"
    __table_args__ = (
        UniqueConstraint("experiment_id", "source_id", name="uq_experiment_candidate_source"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("experiment_attempts.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(100))
    ordinal: Mapped[int]
    name: Mapped[str] = mapped_column(String(160))
    proposal_smiles: Mapped[str] = mapped_column(Text)
    canonical_smiles: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40))
    selected_pose_id: Mapped[str | None] = mapped_column(String(36))
    record: Mapped[dict[str, Any]] = mapped_column(JSON)


class PreparedMolecule(Base):
    __tablename__ = "experiment_prepared_molecules"
    __table_args__ = (
        UniqueConstraint("candidate_id", "source_id", name="uq_prepared_candidate_source"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("experiment_candidates.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(120))
    smiles: Mapped[str] = mapped_column(Text)
    preparation: Mapped[dict[str, Any]] = mapped_column(JSON)


class Pose(Base):
    __tablename__ = "experiment_poses"
    __table_args__ = (
        UniqueConstraint("candidate_id", "source_id", name="uq_pose_candidate_source"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("experiment_candidates.id"), index=True)
    prepared_molecule_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_prepared_molecules.id"), index=True
    )
    target_preparation_id: Mapped[str] = mapped_column(
        ForeignKey("target_preparations.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(String(120))
    sdf_artifact_id: Mapped[str] = mapped_column(ForeignKey("experiment_artifacts.id"), index=True)
    view_artifact_id: Mapped[str] = mapped_column(ForeignKey("experiment_artifacts.id"), index=True)
    origin: Mapped[str] = mapped_column(String(20), default="predicted")
    coordinate_frame: Mapped[str] = mapped_column(String(120))


class PoseEvaluation(Base):
    __tablename__ = "experiment_pose_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pose_id: Mapped[str] = mapped_column(ForeignKey("experiment_poses.id"), unique=True)
    protocol_hash: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)


class ExperimentEvent(Base):
    __tablename__ = "experiment_events"
    __table_args__ = (
        UniqueConstraint("experiment_id", "sequence", name="uq_experiment_event_seq"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    sequence: Mapped[int]
    type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExperimentDecision(Base):
    __tablename__ = "experiment_decisions"
    __table_args__ = (
        UniqueConstraint("experiment_id", "candidate_id", name="uq_experiment_decision"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("experiment_candidates.id"), index=True)
    pinned: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    preferred_pose_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiment_poses.id"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revision: Mapped[int] = mapped_column(default=1, server_default="1")


class ExperimentWorkerHeartbeat(Base):
    __tablename__ = "experiment_worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    health: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ExperimentStudy(Base):
    __tablename__ = "experiment_studies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    label: Mapped[str] = mapped_column(String(160))
    base_spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    seed_pairs: Mapped[list[dict[str, int]]] = mapped_column(JSON)
    spec_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StudyMember(Base):
    __tablename__ = "experiment_study_members"
    __table_args__ = (UniqueConstraint("study_id", "ordinal", name="uq_study_member_ordinal"),)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), primary_key=True)
    study_id: Mapped[str] = mapped_column(ForeignKey("experiment_studies.id"), index=True)
    ordinal: Mapped[int]


@event.listens_for(ExperimentStudy, "before_update")
def immutable_study(_mapper: Any, _connection: Any, target: ExperimentStudy) -> None:
    if any(
        inspect(target).attrs[key].history.has_changes()
        for key in ("label", "base_spec", "seed_pairs", "spec_hash", "request_hash")
    ):
        raise ValueError("Study design is immutable; create a new study instead.")


@event.listens_for(Experiment, "before_update")
def immutable_experiment_intent(_mapper: Any, _connection: Any, target: Experiment) -> None:
    state = inspect(target)
    for key in (
        "spec",
        "spec_hash",
        "request_hash",
        "target_preparation_id",
        "parent_experiment_id",
    ):
        if state.attrs[key].history.has_changes():
            raise ValueError("Experiment intent is immutable; fork a new experiment instead.")
