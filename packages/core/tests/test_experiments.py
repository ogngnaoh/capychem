"""Contract and recovery tests; set CAPYCHEM_TEST_DATABASE_URL for real Postgres.

Each Postgres test owns a temporary schema in an explicitly named *_test DB.
SQLite is only the convenience default, never evidence for SKIP LOCKED behavior.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from capychem.db.models import Base
from capychem.db.session import make_engine
from capychem.experiments.artifacts import publish_file, sha256_file, verified_path
from capychem.experiments.models import (
    Artifact,
    Experiment,
    ExperimentAttempt,
    ExperimentTask,
)
from capychem.experiments.queue import claim_next, finish, heartbeat, record_progress, renew
from capychem.experiments.routes import router
from capychem.experiments.runtime import configuration_fingerprint, probe_command
from capychem.experiments.schemas import CreateExperiment
from capychem.experiments.science import normalize_spec
from capychem.experiments.science_config import MAX_RANDOM_SEED, MAX_SMILES_LENGTH
from capychem.experiments.service import canonical_hash, ingest_report, submit
from capychem.experiments.worker import execute
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def database(tmp_path, monkeypatch):
    url = os.environ.get("CAPYCHEM_TEST_DATABASE_URL")
    monkeypatch.setenv("CAPYCHEM_ARTIFACT_DIR", str(tmp_path / "store"))
    schema = f"experiment_test_{uuid.uuid4().hex}"
    admin = None
    if url:
        if not url.split("?")[0].endswith("_test"):
            pytest.fail("Use a dedicated database whose name ends in _test.")
        admin = create_async_engine(url)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sm
    finally:
        await engine.dispose()
        if admin:
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()


@pytest.fixture
async def client(database):
    app = FastAPI()
    app.state.sessionmaker = database
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def intent(label="A CDK2 test"):
    return CreateExperiment(
        label=label,
        candidate_source={
            "kind": "supplied",
            "candidates": [{"name": "NU2058", "smiles": "Nc1nc(OCC2CCCCC2)c2nc[nH]c2n1"}],
        },
    )


async def test_database_sessions_use_utc():
    url = os.environ.get("CAPYCHEM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Session timezone is a Postgres behavior.")
    engine = make_engine(url)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SHOW timezone")) == "UTC"
    finally:
        await engine.dispose()


async def test_idempotency_preserves_intent_and_rejects_changed_payload(client, database):
    body = intent().model_dump(mode="json")
    first = await client.post("/experiments", json=body, headers={"Idempotency-Key": "same"})
    assert first.status_code == 201
    second = await client.post("/experiments", json=body, headers={"Idempotency-Key": "same"})
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    changed = {**body, "label": "Different intent"}
    conflict = await client.post("/experiments", json=changed, headers={"Idempotency-Key": "same"})
    assert conflict.status_code == 409
    async with database() as session:
        row = await session.get(Experiment, first.json()["id"])
        row.spec = {"changed": True}
        with pytest.raises(ValueError, match="immutable"):
            await session.commit()


async def test_unknown_fields_and_target_are_rejected(client):
    body = intent().model_dump(mode="json")
    assert (await client.post("/experiments", json={**body, "surprise": True})).status_code == 422
    assert (
        await client.post("/experiments", json={**body, "target_preparation_id": "unknown"})
    ).status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"candidate_source": {"kind": "libinvent", "seed": MAX_RANDOM_SEED + 1}},
        {"seeds": {"embedding": MAX_RANDOM_SEED + 1}},
        {"seeds": {"vina": MAX_RANDOM_SEED + 1}},
        {"constraints": {"formal_charge": 1}},
    ],
)
async def test_unsupported_science_settings_are_rejected_before_queueing(client, database, change):
    body = {**intent().model_dump(mode="json"), **change}
    assert (await client.post("/experiments", json=body)).status_code == 422
    async with database() as session:
        assert await session.scalar(select(ExperimentTask)) is None


@pytest.mark.parametrize(
    "change",
    [
        {"target_preparation_id": "cdk2_1h1s_nu6094_v1"},
        {"protocol": "guided_growth_cdk2_v2"},
    ],
)
async def test_crossed_preparation_protocol_pairs_are_rejected(client, database, change):
    body = {**intent().model_dump(), **change}
    assert (await client.post("/experiments", json=body)).status_code == 422
    async with database() as session:
        assert await session.scalar(select(ExperimentTask)) is None


async def test_registered_presets_freeze_each_preparation_and_recommend_growth(client, database):
    response = (await client.get("/experiments/presets")).json()
    assert response["default_preset_id"] == "cdk2_1h1s_nu6094_v1"
    assert [p["id"] for p in response["presets"]] == ["cdk2_1h1s_nu6094_v1", "cdk2_1h1p"]
    for preset in response["presets"]:
        body = preset["default_spec"]
        submitted = await client.post("/experiments", json=body)
        assert submitted.status_code == 201, submitted.text
        saved = submitted.json()["spec"]
        assert saved["target_preparation_id"] == preset["id"]
        assert saved["resolved_protocol"]["target_preparation_id"] == preset["id"]
        assert (
            saved["resolved_protocol"]["target_manifest_sha256"]
            == preset["manifest"]["manifest_sha256"]
        )
        assert (
            saved["resolved_protocol"]["wall_time_limit_seconds"]
            > saved["limits"]["evaluation_admission_seconds"]
        )
    assert response["presets"][0]["receptor_pdb_id"] == "1H1S"
    assert (
        response["presets"][0]["default_spec"]["limits"]["embedding_attempts_per_candidate"] == 16
    )
    assert response["presets"][0]["parent"]["name"] == "NU6094"


def test_public_contract_boundaries_are_accepted_by_science():
    for source in [
        {"kind": "libinvent", "seed": MAX_RANDOM_SEED},
        {
            "kind": "supplied",
            "candidates": [{"name": "a" * 160, "smiles": "C" * MAX_SMILES_LENGTH}],
        },
    ]:
        request = CreateExperiment.model_validate(
            {
                "label": "a" * 160,
                "candidate_source": source,
                "seeds": {"embedding": MAX_RANDOM_SEED, "vina": MAX_RANDOM_SEED},
                "constraints": {"max_clogp": -5, "max_rotatable_bonds": 0},
            }
        )
        normalized = normalize_spec(request.model_dump(mode="json"))
        assert normalized["candidate_source"] == request.model_dump()["candidate_source"]
        assert normalized["label"] == request.label
        assert normalized["constraints"]["max_rotatable_bonds"] == 0


async def test_parallel_idempotency_is_atomic(database):
    if not os.environ.get("CAPYCHEM_TEST_DATABASE_URL"):
        pytest.skip("Concurrent claims require actual Postgres.")
    results = await asyncio.gather(*(submit(database, intent(), "race") for _ in range(5)))
    assert len({row.id for row, _ in results}) == 1
    assert sum(created for _, created in results) == 1


async def test_claim_reclaim_fences_old_attempt(database):
    row, _ = await submit(database, intent(), None)
    first = await claim_next(database, "first")
    assert first and first.experiment_id == row.id
    assert await claim_next(database, "second") is None
    async with database() as session:
        await session.execute(
            update(ExperimentTask)
            .where(ExperimentTask.id == first.task_id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=5))
        )
        await session.commit()
    second = await claim_next(database, "second")
    assert second and second.attempt_id != first.attempt_id
    assert not await record_progress(database, first, {"type": "bad.write"})
    assert not await finish(database, first, "completed")
    assert await record_progress(database, second, {"type": "progress", "stage": "evaluate"})
    assert await finish(database, second, "completed")
    async with database() as session:
        attempts = (
            await session.scalars(select(ExperimentAttempt).order_by(ExperimentAttempt.number))
        ).all()
        assert [a.status for a in attempts] == ["abandoned", "completed"]


async def test_concurrent_workers_claim_distinct_jobs(database):
    if not os.environ.get("CAPYCHEM_TEST_DATABASE_URL"):
        pytest.skip("SKIP LOCKED requires actual Postgres.")
    await submit(database, intent("one"), None)
    await submit(database, intent("two"), None)
    claims = await asyncio.gather(claim_next(database, "a"), claim_next(database, "b"))
    assert all(claims)
    assert len({c.experiment_id for c in claims}) == 2


async def test_cancel_is_durable_for_separate_worker(client, database):
    row, _ = await submit(database, intent(), None)
    claim = await claim_next(database, "worker")
    assert claim
    result = await client.post(f"/experiments/{row.id}/cancel")
    assert result.json()["cancel_requested"] is True
    assert await renew(database, claim) == (True, True)
    assert await finish(database, claim, "completed")
    detail = (await client.get(f"/experiments/{row.id}")).json()
    assert detail["status"] == "cancelled"
    assert detail["outcome"]["kind"] == "insufficient_evidence"
    assert detail["outcome"]["execution_complete"] is False


async def test_cancel_before_claim_does_not_start_work(client, database):
    row, _ = await submit(database, intent(), None)
    result = await client.post(f"/experiments/{row.id}/cancel")
    cancelled = result.json()
    assert cancelled["outcome"]["objective_status"] == "not_assessed"
    assert cancelled["outcome"]["execution_complete"] is False
    assert await claim_next(database, "worker") is None
    latest = (await client.get(f"/experiments/{row.id}")).json()
    assert latest["outcome"] == cancelled["outcome"]
    assert latest["finished_at"] == cancelled["finished_at"]
    assert latest["latest_sequence"] == cancelled["latest_sequence"]
    events = (await client.get(f"/experiments/{row.id}/events")).json()["events"]
    assert [event["type"] for event in events] == [
        "experiment.queued",
        "cancel.requested",
        "experiment.finished",
    ]
    async with database() as session:
        task = await session.scalar(select(ExperimentTask))
        assert task.status == "cancelled" and task.attempt_number == 0


async def test_events_replay_without_notification_delivery(client, database):
    row, _ = await submit(database, intent(), None)
    claim = await claim_next(database, "worker")
    for n in range(3):
        assert await record_progress(database, claim, {"type": "candidate.complete", "index": n})
    events = (await client.get(f"/experiments/{row.id}/events?after=0&limit=2")).json()
    assert [e["seq"] for e in events["events"]] == [1, 2]
    catchup = (
        await client.get(f"/experiments/{row.id}/events?after={events['next_sequence']}")
    ).json()
    assert [e["seq"] for e in catchup["events"]] == [3, 4, 5]


def minimal_report(directory: Path, spec: dict):
    (directory / "inputs").mkdir(exist_ok=True)
    (directory / "inputs/request.json").write_text(json.dumps(spec))
    (directory / "inputs/protocol.json").write_text(json.dumps({"id": spec["protocol"]}))
    (directory / "pose.sdf").write_text("exact coordinate artifact\n")
    (directory / "view.json").write_text(
        json.dumps({"id": "source-pose", "origin": "predicted", "contacts": []})
    )
    report = {
        "schema_version": 1,
        "kind": "live_computation",
        "status": "complete",
        "request_spec": spec,
        "protocol_manifest": {"id": spec["protocol"]},
        "provenance": {
            "request_spec_sha256": canonical_hash(spec),
            "engine_fingerprint": spec["resolved_protocol"]["engine_fingerprint"],
            "protocol_sha256": sha256_file(directory / "inputs/protocol.json"),
        },
        "target": {
            "id": spec["target_preparation_id"],
            "frame": spec["resolved_protocol"]["frame"],
        },
        "records": [
            {
                "id": "raw-0",
                "name": "proposal",
                "proposal_smiles": "CC",
                "canonical_smiles": "CC",
                "status": "ready_for_review",
                "prepared_states": [{"id": "state", "smiles": "CC"}],
                "selected_pose_id": "pose",
                "poses": [
                    {
                        "id": "pose",
                        "prepared_state_id": "state",
                        "prepared_smiles": "CC",
                        "sdf": "pose.sdf",
                        "view_json": "view.json",
                        "score": -5.0,
                        "geometry_pass": True,
                        "review_ready": True,
                        "asp86_contact": False,
                        "contacts": [],
                        "ring_drift_A": 0.5,
                    }
                ],
                "pose_errors": [],
            },
            {
                "id": "raw-1",
                "name": "invalid",
                "proposal_smiles": "not a molecule",
                "properties": None,
                "status": "invalid",
                "poses": [],
            },
        ],
        "summary": {},
    }
    (directory / "report.json").write_text(json.dumps(report))
    return report


async def test_results_identity_decisions_exports_and_integrity(client, database, tmp_path):
    row, _ = await submit(database, intent(), None)
    claim = await claim_next(database, "worker")
    assert claim
    directory = tmp_path / "science"
    directory.mkdir()
    report = minimal_report(directory, claim.spec)
    assert await ingest_report(database, claim, directory, report, final=True)
    candidates = (await client.get(f"/experiments/{row.id}/candidates")).json()["items"]
    assert len(candidates) == 2 and candidates[1]["status"] == "invalid"
    pose_id = candidates[0]["structureId"]
    structures = (await client.get(f"/experiments/{row.id}/viewer")).json()["structures"]
    assert structures[0]["id"] == pose_id
    assert (await client.get(structures[0]["sdfUrl"])).text == "exact coordinate artifact\n"
    bad = await client.put(
        f"/experiments/{row.id}/decisions/{candidates[1]['id']}",
        json={"preferred_pose_id": pose_id},
    )
    assert bad.status_code == 422
    saved = await client.put(
        f"/experiments/{row.id}/decisions/{candidates[0]['id']}",
        json={"pinned": True, "notes": "Review this pose", "preferred_pose_id": pose_id},
    )
    assert saved.status_code == 200
    exported = (await client.get(f"/experiments/{row.id}/export")).json()
    assert exported["decisions"][0]["notes"] == "Review this pose"
    assert len(exported["artifacts"]) == 5
    assert {a["relative_path"] for a in exported["artifacts"]} == {
        "pose.sdf",
        "view.json",
        "report.json",
        "inputs/request.json",
        "inputs/protocol.json",
    }
    artifact_id = structures[0]["sdfUrl"].rsplit("/", 1)[-1]
    async with database() as session:
        artifact = await session.get(Artifact, artifact_id)
        path = verified_path(artifact.storage_key, artifact.sha256, artifact.size_bytes)
        path.write_text("tampered")
    assert (await client.get(structures[0]["sdfUrl"])).status_code == 409


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"unspecified_stereo": [{"type": "Atom_Tetrahedral", "index": 1}]},
        {
            "prepared_states": [
                {"id": "state", "smiles": "CC", "proposal_had_unspecified_stereo": True}
            ]
        },
    ],
)
async def test_stereo_warning_reaches_live_candidates_and_export(
    client, database, tmp_path, metadata
):
    row, _ = await submit(database, intent(), None)
    claim = await claim_next(database, "worker")
    directory = tmp_path / "science"
    directory.mkdir()
    report = minimal_report(directory, claim.spec)
    report["records"][0].update(metadata)
    (directory / "report.json").write_text(json.dumps(report))
    assert await ingest_report(database, claim, directory, report, final=True)
    candidates = (await client.get(f"/experiments/{row.id}/candidates")).json()["items"]
    exported = (await client.get(f"/experiments/{row.id}/export")).json()
    for candidate in [candidates[0], exported["candidates"][0]]:
        assert candidate["unspecifiedStereochemistry"] == bool(metadata)
        if metadata:
            assert "not exhaustively sampled" in candidate["stereochemistryNote"]
            assert "not a resolved input identity" in candidate["stereochemistryNote"]
        else:
            assert candidate["stereochemistryNote"] is None
    artifact = next(a for a in exported["artifacts"] if a["relative_path"] == "report.json")
    assert (await client.get(artifact["url"])).json() == report


async def test_candidate_exclusion_provenance_survives_recovery(client, database, tmp_path):
    row, _ = await submit(database, intent(), None)
    first = await claim_next(database, "first")
    assert first
    report = minimal_report(tmp_path, first.spec)
    report["records"][1]["error"] = "SMILES could not be parsed"
    report["records"].extend(
        [
            {
                "id": "raw-duplicate",
                "name": "Normalized duplicate",
                "proposal_smiles": "C(C)",
                "canonical_smiles": "C(C)",
                "normalized_smiles": "CC",
                "status": "duplicate",
                "duplicate_of": "raw-0",
                "poses": [],
            },
            {
                "id": "raw-missing-reference",
                "proposal_smiles": "CC",
                "canonical_smiles": "CC",
                "status": "duplicate",
                "duplicate_of": "missing-source",
                "poses": [],
            },
        ]
    )
    (tmp_path / "report.json").write_text(json.dumps(report))
    assert await ingest_report(database, first, tmp_path, report, final=True)

    def check_candidates(items):
        original, invalid, duplicate, missing = items
        assert duplicate["smiles"] != original["smiles"]
        assert duplicate["duplicateOfSourceId"] == "raw-0"
        assert duplicate["duplicateOfCandidateId"] == original["id"]
        assert invalid["error"] == "SMILES could not be parsed"
        assert invalid["duplicateOfCandidateId"] is None
        assert original["error"] is None and original["duplicateOfSourceId"] is None
        assert missing["duplicateOfSourceId"] == "missing-source"
        assert missing["duplicateOfCandidateId"] is None  # No SMILES-based inference.
        return original["id"]

    old_id = check_candidates(
        (await client.get(f"/experiments/{row.id}/candidates")).json()["items"]
    )
    async with database() as session:
        await session.execute(
            update(ExperimentTask).values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=5))
        )
        await session.commit()
    second = await claim_next(database, "second")
    assert second
    assert await ingest_report(database, second, tmp_path, report, final=True)
    active = (await client.get(f"/experiments/{row.id}/candidates")).json()["items"]
    new_id = check_candidates(active)
    assert new_id != old_id
    assert active[0]["sourceId"] != active[2]["duplicateOfSourceId"]
    history = (
        await client.get(
            f"/experiments/{row.id}/candidates", params={"attempt_id": first.attempt_id}
        )
    ).json()["items"]
    assert check_candidates(history) == old_id
    exported = (await client.get(f"/experiments/{row.id}/export")).json()
    assert [check_candidates(a["candidates"]) for a in exported["attempts"]] == [old_id, new_id]


@pytest.mark.parametrize("all_embeddings_failed", [False, True])
async def test_worker_preserves_embedding_failure_outcome_and_evidence(
    client, database, monkeypatch, all_embeddings_failed
):
    """Exercise worker publication with a controlled subprocess, without chemistry tools."""
    row, _ = await submit(database, intent(), None)
    claim = await claim_next(database, "worker")
    assert claim
    original_create = asyncio.create_subprocess_exec

    async def controlled_science(*args, **kwargs):
        directory = Path(args[-1])
        report = minimal_report(directory, claim.spec)
        record = report["records"][0]
        record.update(
            evaluated=True,
            partial=True,
            embedding_attempts=[
                {"attempt": 0, "seed": 194715, "status": "failed", "error": "Cannot embed"}
            ],
        )
        if all_embeddings_failed:
            record.update(status="no_pose", poses=[], prepared_states=[], selected_pose_id=None)
        report.update(status="complete", execution_outcome="completed_with_errors")
        (directory / "report.json").write_text(json.dumps(report))
        return await original_create(
            sys.executable,
            "-c",
            'print(\'{"type": "experiment.complete", "stage": "complete"}\')',
            **kwargs,
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", controlled_science)
    await execute(database, claim)
    detail = (await client.get(f"/experiments/{row.id}")).json()
    assert detail["status"] == "completed_with_errors"
    assert detail["counts"]["evaluated"] == 1
    assert detail["counts"]["embedding_errors"] == 1
    assert detail["counts"]["pose_errors"] == 0
    candidate = (await client.get(f"/experiments/{row.id}/candidates")).json()["items"][0]
    assert candidate["partial"] is True
    assert candidate["embeddingErrors"][0]["error"] == "Cannot embed"
    assert candidate["poseCount"] == (0 if all_embeddings_failed else 1)
    exported = (await client.get(f"/experiments/{row.id}/export")).json()
    assert exported["attempts"][0]["status"] == "completed_with_errors"


def test_artifact_paths_cannot_escape_attempt_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPYCHEM_ARTIFACT_DIR", str(tmp_path / "store"))
    base = tmp_path / "attempt"
    base.mkdir()
    (tmp_path / "outside.sdf").write_text("outside")
    with pytest.raises(ValueError, match="inside"):
        publish_file(base, "../outside.sdf", "experiment", "attempt")


def test_artifact_aliases_share_identity_and_names_keep_directory_context(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPYCHEM_ARTIFACT_DIR", str(tmp_path / "store"))
    base = tmp_path / "attempt"
    (base / "poses").mkdir(parents=True)
    (base / "inputs").mkdir()
    (base / "poses/shared.sdf").write_text("same content")
    (base / "inputs/shared.sdf").write_text("same content")
    pose = publish_file(base, "poses/shared.sdf", "experiment", "attempt")
    alias = publish_file(base, "inputs/../poses/shared.sdf", "experiment", "attempt")
    source = publish_file(base, "inputs/shared.sdf", "experiment", "attempt")
    assert pose["id"] == alias["id"]
    assert pose["id"] != source["id"]
    assert pose["storage_key"] == source["storage_key"]
    assert pose["relative_path"] == "poses/shared.sdf"
    assert source["relative_path"] == "inputs/shared.sdf"


@pytest.mark.parametrize(
    "change",
    [
        {"limits": {"embedding_attempts_per_candidate": True}},
        {"limits": {"max_unique_candidates_evaluated": "2"}},
        {"seeds": {"vina": 2.0}},
        {"schema_version": True},
        {"constraints": {"formal_charge": False}},
        {"parent_experiment_id": ""},
    ],
)
async def test_malformed_typed_intent_never_creates_jobs(client, database, change):
    result = await client.post("/experiments", json={**intent().model_dump(), **change})
    assert result.status_code == 422
    async with database() as session:
        assert await session.scalar(select(ExperimentTask)) is None


async def test_cursor_pagination_remains_stable_during_new_submissions(client, database):
    old = [await submit(database, intent(f"Series {n}"), None) for n in range(5)]
    first = (await client.get("/experiments?limit=2&q=Series&status=queued")).json()
    assert first["has_more"] is True
    new, _ = await submit(database, intent("Series new"), None)
    seen = [r["id"] for r in first["items"]]
    cursor = first["next_cursor"]
    for _ in range(5):
        if cursor is None:
            break
        page = (
            await client.get(
                "/experiments",
                params={
                    "limit": 2,
                    "q": "Series",
                    "status": "queued",
                    "cursor": cursor,
                },
            )
        ).json()
        seen.extend(r["id"] for r in page["items"])
        cursor = page["next_cursor"]
    assert cursor is None, "Pagination must terminate without repeating a page"
    assert len(seen) == len(set(seen)), "Existing entries must not repeat between pages"
    assert {row.id for row, _ in old} <= set(seen)
    # A keyset cursor is not a database snapshot: an insert sharing SQLite's
    # second-resolution timestamp can sort below the cursor's UUID tie-breaker.
    assert set(seen) <= {row.id for row, _ in old} | {new.id}
    assert (
        await client.get(
            "/experiments",
            params={
                "cursor": first["next_cursor"],
                "q": "Other",
            },
        )
    ).status_code == 422
    assert (await client.get("/experiments?cursor=not-json")).status_code == 422
    assert (await client.get("/experiments?status=unknown")).status_code == 422


@pytest.mark.parametrize("identifier", [123, {}, []])
async def test_typed_malformed_cursor_returns_422(client, identifier):
    cursor = base64.urlsafe_b64encode(
        json.dumps(
            {
                "filters": canonical_hash({"status": None, "q": ""}),
                "created_at": "2026-11-17T00:00:00+00:00",
                "id": identifier,
            }
        ).encode()
    ).decode()
    result = await client.get("/experiments", params={"cursor": cursor})
    assert result.status_code == 422


async def test_lease_expiring_during_lock_wait_cannot_publish(database):
    if not os.environ.get("CAPYCHEM_TEST_DATABASE_URL"):
        pytest.skip("Row lock timing requires PostgreSQL")
    await submit(database, intent(), None)
    claim = await claim_next(database, "waiting-worker")
    async with database() as session:
        task = await session.get(ExperimentTask, claim.task_id)
        task.lease_expires_at = datetime.now(UTC) + timedelta(seconds=0.3)
        await session.commit()
    async with database() as holder:
        await holder.scalar(
            select(ExperimentTask).where(ExperimentTask.id == claim.task_id).with_for_update()
        )
        blocked = asyncio.create_task(record_progress(database, claim, {"type": "expired.write"}))
        await asyncio.sleep(0.4)
        assert not blocked.done()
        await holder.commit()
    assert await blocked is False


@pytest.mark.parametrize("mutation", ["score", "coordinates", "prepared_state", "selected_pose"])
async def test_published_pose_identity_cannot_be_rewritten(client, database, tmp_path, mutation):
    row, _ = await submit(database, intent(), None)
    claim = await claim_next(database, "worker")
    report = minimal_report(tmp_path, claim.spec)
    await ingest_report(database, claim, tmp_path, report)
    changed = copy.deepcopy(report)
    if mutation == "score":
        changed["records"][0]["poses"][0]["score"] = -99
    elif mutation == "coordinates":
        (tmp_path / "pose.sdf").write_text("different coordinates\n")
    elif mutation == "prepared_state":
        changed["records"][0]["prepared_states"][0]["smiles"] = "CCC"
    else:
        changed["records"][0]["selected_pose_id"] = "missing"
    with pytest.raises(ValueError):
        await ingest_report(database, claim, tmp_path, changed)
    candidate = (await client.get(f"/experiments/{row.id}/candidates")).json()["items"][0]
    assert candidate["score"] == -5
    assert (await client.get(candidate["poses"][0]["sdfUrl"])).text == "exact coordinate artifact\n"


@pytest.mark.parametrize("field", ["request_spec", "target", "protocol_manifest", "provenance"])
async def test_mismatched_report_provenance_is_not_published(database, tmp_path, field):
    await submit(database, intent(), None)
    claim = await claim_next(database, "worker")
    report = minimal_report(tmp_path, claim.spec)
    report[field] = {}
    with pytest.raises(ValueError):
        await ingest_report(database, claim, tmp_path, report)
    async with database() as session:
        assert await session.scalar(select(Artifact)) is None


async def test_reclaimed_attempt_hides_old_projection_but_preserves_review_history(
    client, database, tmp_path
):
    row, _ = await submit(database, intent(), None)
    first = await claim_next(database, "first")
    report = minimal_report(tmp_path, first.spec)
    await ingest_report(database, first, tmp_path, report, final=True)
    old = (await client.get(f"/experiments/{row.id}/candidates")).json()["items"][0]
    await client.put(f"/experiments/{row.id}/decisions/{old['id']}", json={"notes": "Keep history"})
    async with database() as session:
        await session.execute(
            update(ExperimentTask).values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=5))
        )
        await session.commit()
    second = await claim_next(database, "second")
    assert (await client.get(f"/experiments/{row.id}/candidates")).json()["items"] == []
    detail = (await client.get(f"/experiments/{row.id}")).json()
    assert detail["counts"]["active_attempt_id"] == second.attempt_id
    assert detail["counts"]["poses"] == 0
    assert (
        await client.get(
            f"/experiments/{row.id}/viewer",
            params={
                "attempt_id": first.attempt_id,
                "pose_id": old["structureId"],
            },
        )
    ).status_code == 200
    await ingest_report(database, second, tmp_path, report, final=True)
    new = (await client.get(f"/experiments/{row.id}/candidates")).json()["items"][0]
    assert new["id"] != old["id"] and new["structureId"] != old["structureId"]
    exported = (await client.get(f"/experiments/{row.id}/export")).json()
    assert [len(a["candidates"]) for a in exported["attempts"]] == [2, 2]
    assert exported["decisions"][0]["notes"] == "Keep history"
    assert not await ingest_report(database, first, tmp_path, {"invalid": "stale"})


async def test_concurrent_decision_updates_require_matching_revision(client, database, tmp_path):
    if not os.environ.get("CAPYCHEM_TEST_DATABASE_URL"):
        pytest.skip("Concurrent row serialization requires PostgreSQL")
    row, _ = await submit(database, intent(), None)
    claim = await claim_next(database, "worker")
    await ingest_report(database, claim, tmp_path, minimal_report(tmp_path, claim.spec))
    candidate = (await client.get(f"/experiments/{row.id}/candidates")).json()["items"][0]
    url = f"/experiments/{row.id}/decisions/{candidate['id']}"
    results = await asyncio.gather(
        *[
            client.patch(url, json={"notes": note}, headers={"If-Match": '"0"'})
            for note in ("A", "B")
        ]
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    saved = next(r.json() for r in results if r.status_code == 200)
    conflict = next(r.json() for r in results if r.status_code == 409)
    assert conflict["detail"]["current"]["notes"] == saved["notes"]
    patched = await client.patch(url, json={"pinned": True}, headers={"If-Match": '"1"'})
    assert patched.json()["notes"] == saved["notes"]
    assert patched.json()["revision"] == 2 and patched.headers["etag"] == '"2"'
    assert (await client.patch(url, json={"pinned": False})).status_code == 428


async def test_readiness_requires_matching_verified_worker_runtime(client, database, monkeypatch):
    monkeypatch.setattr(
        "capychem.experiments.science_config.readiness",
        lambda: {
            "configured": True,
            "problems": [],
            "libinvent_configured": True,
        },
    )
    await heartbeat(database, "old-worker")
    result = (await client.get("/experiments/readiness")).json()
    assert result["ready"] is False and result["capabilities"]["libinvent"] is False
    health = {
        "state": "ready",
        "configuration_fingerprint": configuration_fingerprint(),
        "science": {"ok": True},
        "generator": {"ok": True},
    }
    await heartbeat(database, "verified-worker", health)
    assert (await client.get("/experiments/readiness")).json()["ready"] is True
    monkeypatch.setenv("CAPYCHEM_VINA_BINARY", "/another/vina")
    result = (await client.get("/experiments/readiness")).json()
    assert result["ready"] is False and result["capabilities"]["libinvent"] is False


async def test_attempt_storage_error_becomes_failed_job_without_killing_worker(
    client, database, monkeypatch
):
    row, _ = await submit(database, intent(), None)
    claim = await claim_next(database, "worker")

    def unavailable(_attempt):
        raise PermissionError("Artifact store is read-only")

    monkeypatch.setattr("capychem.experiments.worker.attempt_directory", unavailable)
    await execute(database, claim)
    result = (await client.get(f"/experiments/{row.id}")).json()
    assert result["status"] == "failed"
    assert "read-only" in result["error"]
    await submit(database, intent("Next job"), None)
    assert await claim_next(database, "worker") is not None


async def test_runtime_probe_is_bounded():
    with pytest.raises(TimeoutError):
        await probe_command([sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.1)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group lifetime check")
async def test_worker_lifetime_pipe_terminates_scientific_descendants():
    child = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable,'-c',"
        "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)']); "
        "print('ready',flush=True); time.sleep(60)"
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "capychem.experiments.supervisor",
        "--",
        sys.executable,
        "-c",
        child,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        assert await asyncio.wait_for(process.stdout.readline(), 5) == b"ready\n"
        process.stdin.close()  # The same EOF the OS sends after an owning worker is killed.
        await asyncio.wait_for(process.communicate(), 5)
        assert process.returncode != 0
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def test_supervisor_success_does_not_wait_for_parent_pipe_close():
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "capychem.experiments.supervisor",
        "--",
        sys.executable,
        "-c",
        "print('complete')",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        # Keep stdin open: the owner is alive while its scientific process exits.
        await asyncio.wait_for(process.wait(), 5)
        assert process.returncode == 0, await process.stderr.read()
        assert await process.stdout.read() == b"complete\n"
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


@pytest.mark.parametrize("numeric", ["NaN", "Infinity", "-Infinity"])
async def test_nonfinite_json_numeric_returns_actionable_422(client, database, numeric):
    body = json.dumps(intent().model_dump())
    body = body.replace('"max_clogp": 4.5', f'"max_clogp": {numeric}')
    response = await client.post(
        "/experiments", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "constraints", "max_clogp"]
    async with database() as session:
        assert await session.scalar(select(ExperimentTask)) is None


async def test_missing_reference_setup_is_503_and_idempotent_reads_still_work(
    client, database, monkeypatch, tmp_path
):
    body = intent().model_dump()
    first = await client.post("/experiments", json=body, headers={"Idempotency-Key": "existing"})
    monkeypatch.setenv("CAPYCHEM_CDK2_DATA_DIR", str(tmp_path / "missing"))
    repeated = await client.post("/experiments", json=body, headers={"Idempotency-Key": "existing"})
    assert repeated.status_code == 200 and repeated.json()["id"] == first.json()["id"]
    result = await client.post("/experiments", json=body)
    assert result.status_code == 503
    async with database() as session:
        assert len((await session.scalars(select(ExperimentTask))).all()) == 1


@pytest.mark.parametrize("stop_reason", ["cancel", "lease_expiry", "timeout"])
async def test_worker_stops_running_process_and_preserves_partial_results(
    client, database, monkeypatch, stop_reason
):
    row, _ = await submit(database, intent(), None)
    claim = await claim_next(database, "worker")
    original_create = asyncio.create_subprocess_exec
    children = []
    clock = [0]
    if stop_reason == "timeout":
        monkeypatch.setattr("capychem.experiments.worker.monotonic", lambda: clock[0])

    async def controlled_science(*args, **kwargs):
        directory = Path(args[-1])
        report = minimal_report(directory, claim.spec)
        report["status"] = "running"
        (directory / "report.json").write_text(json.dumps(report))
        process = await original_create(
            sys.executable,
            "-c",
            'import time; print(\'{"type":"candidate.complete"}\',flush=True); time.sleep(60)',
            **kwargs,
        )
        children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", controlled_science)
    execution = asyncio.create_task(execute(database, claim))
    try:
        for _ in range(100):
            detail = (await client.get(f"/experiments/{row.id}")).json()
            if detail["counts"].get("poses") == 1:
                break
            await asyncio.sleep(0.02)
        assert detail["counts"]["poses"] == 1
        if stop_reason == "cancel":
            await client.post(f"/experiments/{row.id}/cancel")
        elif stop_reason == "timeout":
            clock[0] = 100000
        else:
            async with database() as session:
                await session.execute(
                    update(ExperimentTask).values(
                        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1)
                    )
                )
                await session.commit()
        await asyncio.wait_for(execution, 6)
        assert children[0].returncode is not None
        detail = (await client.get(f"/experiments/{row.id}")).json()
        assert detail["counts"]["poses"] == 1
        if stop_reason == "cancel":
            assert detail["status"] == "cancelled"
            assert detail["outcome"]["execution_complete"] is False
        elif stop_reason == "timeout":
            assert detail["status"] == "failed"
            assert "wall-clock limit" in detail["error"]
            assert detail["outcome"]["kind"] == "insufficient_evidence"
        else:
            replacement = await claim_next(database, "replacement")
            assert replacement and replacement.attempt_id != claim.attempt_id
            assert not await finish(database, claim, "completed")
    finally:
        if not execution.done():
            execution.cancel()
            try:
                await execution
            except asyncio.CancelledError:
                pass
