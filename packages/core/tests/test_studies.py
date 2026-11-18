"""Studies use the existing real Postgres transaction and experiment queue."""

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
import test_experiments
from capychem.experiments import studies
from capychem.experiments.models import Experiment, ExperimentStudy, ExperimentTask
from capychem.experiments.queue import claim_next, finish
from capychem.experiments.routes import router as experiment_router
from capychem.experiments.service import ingest_report
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

database = test_experiments.database
minimal_report = test_experiments.minimal_report


@pytest.fixture
async def client(database):
    app = FastAPI()
    app.state.sessionmaker = database
    app.include_router(experiment_router)
    app.include_router(studies.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def design():
    return {
        "label": "Repeated declared inputs",
        "base_spec": {
            "target_preparation_id": "cdk2_1h1p",
            "protocol": "guided_local_cdk2_v1",
            "candidate_source": {
                "kind": "supplied",
                "candidates": [
                    {"name": "proposal", "smiles": "CC"},
                    {"name": "invalid", "smiles": "not a molecule"},
                ],
            },
        },
        "seed_pairs": [{"embedding": 100, "vina": 42}, {"embedding": 200, "vina": 43}],
    }


async def test_study_atomic_idempotency_and_frozen_members(client, database):
    body = design()
    responses = await asyncio.gather(
        *[
            client.post("/studies", json=body, headers={"Idempotency-Key": "study-create"})
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    study = responses[0].json()
    assert len(study["members"]) == 2
    assert [m["experiment"]["spec"]["seeds"] for m in study["members"]] == body["seed_pairs"]
    assert (
        len(
            {
                m["experiment"]["spec"]["resolved_protocol"]["engine_fingerprint"]
                for m in study["members"]
            }
        )
        == 1
    )
    assert study["candidates"][0]["planned_runs"] == 2
    assert study["candidates"][0]["observed_runs"] == 0
    assert all(o["asp86_contact"] is None for o in study["candidates"][0]["observations"])
    body["seed_pairs"][0]["vina"] = 99
    assert (
        await client.post("/studies", json=body, headers={"Idempotency-Key": "study-create"})
    ).status_code == 409
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(ExperimentStudy)) == 1
        assert await session.scalar(select(func.count()).select_from(ExperimentTask)) == 2


async def test_study_rolls_back_all_jobs_on_member_error(client, database, monkeypatch):
    original = studies.create_in_session
    calls = 0

    async def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("Injected member resolution failure")
        return await original(*args, **kwargs)

    monkeypatch.setattr(studies, "create_in_session", fail_second)
    response = await client.post("/studies", json=design())
    assert response.status_code == 422
    async with database() as session:
        for model in (ExperimentStudy, Experiment, ExperimentTask):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


async def test_study_history_cursor_does_not_repeat_after_new_submission(client):
    original = set()
    for i in range(3):
        original.add(
            (await client.post("/studies", json={**design(), "label": f"Study {i}"})).json()["id"]
        )
    first = (await client.get("/studies?limit=2")).json()
    assert first["has_more"] and first["next_cursor"]
    added = (await client.post("/studies", json={**design(), "label": "New study"})).json()["id"]
    second = (
        await client.get("/studies", params={"limit": 2, "cursor": first["next_cursor"]})
    ).json()
    ids = [row["id"] for row in [*first["items"], *second["items"]]]
    assert len(ids) == len(set(ids)) == 3
    assert set(ids) == original and added not in ids
    assert not second["has_more"] and second["next_cursor"] is None
    assert (await client.get("/studies?cursor=not-a-uuid")).status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"seed_pairs": [{"embedding": 1, "vina": 2}, {"embedding": 1, "vina": 2}]},
        {"seed_pairs": [{"embedding": 1, "vina": 2}]},
        {"base_change": {"candidate_source": {"kind": "libinvent", "raw_proposal_count": 4}}},
        {"base_change": {"protocol": "guided_growth_cdk2_v2"}},
        {"base_change": {"seeds": {"embedding": 1, "vina": 2}}},
        {"base_change": {"schema_version": True}},
    ],
)
async def test_study_rejects_ambiguous_or_unsupported_design(client, database, change):
    body = design()
    change = copy.deepcopy(change)
    body["base_spec"].update(change.pop("base_change", {}))
    body.update(change)
    assert (await client.post("/studies", json=body)).status_code == 422
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Experiment)) == 0


async def test_study_aggregates_selected_evidence_and_preserves_identity(
    client, database, tmp_path
):
    study = (await client.post("/studies", json=design())).json()
    for index in range(2):
        claim = await claim_next(database, f"worker-{index}")
        directory = tmp_path / str(index)
        directory.mkdir()
        report = minimal_report(directory, claim.spec)
        report["records"][0]["normalized_smiles"] = "CC"
        report["records"][0]["unspecified_stereo"] = [
            {"type": "Atom_Tetrahedral", "index": 1}
        ]
        report["records"][0]["poses"][0]["asp86_contact"] = True
        report["records"][0]["poses"][0]["review_ready"] = index == 0
        report["records"][0]["poses"][0]["contacts"] = [
            {
                "residue": "ASP86.A",
                "protein_atom_name": "N",
                "type": "HBAcceptor",
                "distance_A": 3.1,
            },
            {"residue": "LEU83.A", "protein_atom_name": "O", "type": "HBDonor", "distance_A": 2.9},
        ]
        report["records"][1]["error"] = "SMILES could not be parsed"
        (directory / "report.json").write_text(json.dumps(report))
        assert await ingest_report(database, claim, directory, report, final=True)
        assert await finish(database, claim, "completed")
    result = (await client.get(f"/studies/{study['id']}")).json()
    assert result["status"] == "completed"
    candidate, invalid = result["candidates"]
    assert candidate["completed_runs"] == candidate["observed_runs"] == 2
    assert candidate["review_ready_runs"] == candidate["contact_hit_runs"] == 1
    assert all(
        o["asp86_contacts"]
        == [
            {
                "residue": "ASP86.A",
                "protein_atom_name": "N",
                "type": "HBAcceptor",
                "distance_A": 3.1,
            }
        ]
        for o in candidate["observations"]
    )
    assert len({o["candidate_id"] for o in candidate["observations"]}) == 2
    assert all(
        o["unspecified_stereochemistry"]
        and "not exhaustively sampled" in o["stereochemistry_note"]
        for o in candidate["observations"]
    )
    assert all(
        o["normalized_smiles"] == "CC" and o["prepared_state_id"] for o in candidate["observations"]
    )
    assert invalid["observed_runs"] == invalid["contact_hit_runs"] == 0
    assert all(o["asp86_contacts"] is None for o in invalid["observations"])
    assert all(
        o["status"] == "invalid" and o["asp86_contact"] is None for o in invalid["observations"]
    )
    exported = (await client.get(f"/studies/{study['id']}/export")).json()
    assert exported["kind"] == "repeated_seed_study"
    assert len(exported["experiments"]) == 2
    for observation, experiment in zip(
        candidate["observations"], exported["experiments"], strict=True
    ):
        assert observation["experiment_id"] == experiment["experiment"]["id"]
        assert observation["selected_pose_id"] == experiment["candidates"][0]["structureId"]
        assert observation["sdf_url"] in {a["url"] for a in experiment["artifacts"]}


async def test_study_cancel_is_idempotent_and_preserves_completed_work(client, database):
    study = (await client.post("/studies", json=design())).json()
    claim = await claim_next(database, "worker")
    await finish(database, claim, "completed")
    url = f"/studies/{study['id']}/cancel"
    result = (await client.post(url)).json()
    again = (await client.post(url)).json()
    assert result == again
    assert sorted(m["experiment"]["status"] for m in result["members"]) == [
        "cancelled",
        "completed",
    ]
    completed = next(m for m in result["members"] if m["experiment"]["status"] == "completed")
    assert not completed["experiment"]["cancel_requested"]


async def test_shortlist_origin_is_verified_and_retained(client, database, tmp_path):
    study = (await client.post("/studies", json=design())).json()
    claim = await claim_next(database, "worker")
    assert await ingest_report(database, claim, tmp_path, minimal_report(tmp_path, claim.spec))
    candidate = (await client.get(f"/experiments/{claim.experiment_id}/candidates")).json()[
        "items"
    ][0]
    body = {
        **design()["base_spec"],
        "label": "Shortlist round",
        "parent_experiment_id": claim.experiment_id,
        "candidate_source": {
            "kind": "supplied",
            "candidates": [{"name": "Chosen", "smiles": "CC"}],
        },
        "candidate_origins": [
            {
                "candidate_index": 0,
                "experiment_id": claim.experiment_id,
                "candidate_id": candidate["id"],
                "pose_id": candidate["structureId"],
            }
        ],
    }
    created = await client.post("/experiments", json=body)
    assert created.status_code == 201
    assert created.json()["spec"]["candidate_origins"] == body["candidate_origins"]
    body["candidate_source"]["candidates"][0]["smiles"] = "CCC"
    assert (await client.post("/experiments", json=body)).status_code == 422

    body["candidate_source"]["candidates"][0]["smiles"] = "CC"
    body["candidate_origins"][0]["experiment_id"] = next(
        m["experiment"]["id"]
        for m in study["members"]
        if m["experiment"]["id"] != claim.experiment_id
    )
    assert (await client.post("/experiments", json=body)).status_code == 422


async def test_study_uses_active_attempt_and_keeps_duplicate_input_rows(client, database, tmp_path):
    body = design()
    body["base_spec"]["candidate_source"]["candidates"].append(
        {"name": "Duplicate", "smiles": "CC"}
    )
    study = (await client.post("/studies", json=body)).json()
    first = await claim_next(database, "old-worker")
    report = minimal_report(tmp_path, first.spec)
    report["records"][0]["normalized_smiles"] = "CC"
    report["records"][0]["poses"][0]["asp86_contact"] = True
    report["records"].append(
        {
            "id": "duplicate",
            "name": "Duplicate",
            "proposal_smiles": "CC",
            "canonical_smiles": "CC",
            "normalized_smiles": "CC",
            "status": "duplicate",
            "duplicate_of": "raw-0",
            "poses": [],
        }
    )
    (tmp_path / "report.json").write_text(json.dumps(report))
    assert await ingest_report(database, first, tmp_path, report, final=True)
    before = (await client.get(f"/studies/{study['id']}")).json()
    assert before["candidates"][0]["contact_hit_runs"] == 1
    async with database() as session:
        await session.execute(
            update(ExperimentTask)
            .where(ExperimentTask.id == first.task_id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=5))
        )
        await session.commit()
    second = await claim_next(database, "new-worker")
    assert second.experiment_id == first.experiment_id
    replaying = (await client.get(f"/studies/{study['id']}")).json()
    assert replaying["candidates"][0]["contact_hit_runs"] == 0
    assert replaying["candidates"][0]["observed_runs"] == 0
    report["records"][0]["poses"][0]["asp86_contact"] = False
    (tmp_path / "report.json").write_text(json.dumps(report))
    assert await ingest_report(database, second, tmp_path, report, final=True)
    current = (await client.get(f"/studies/{study['id']}")).json()
    assert len(current["candidates"]) == 3
    assert current["candidates"][0]["contact_hit_runs"] == 0
    assert current["candidates"][0]["observed_runs"] == 1
    assert current["candidates"][0]["completed_runs"] == 0  # Still running, evidence is partial.
    duplicate = next(o for o in current["candidates"][2]["observations"] if o["candidate_id"])
    original = next(o for o in current["candidates"][0]["observations"] if o["candidate_id"])
    assert duplicate["duplicate_of_candidate_id"] == original["candidate_id"]
    assert duplicate["attempt_id"] == second.attempt_id
    assert duplicate["asp86_contact"] is None


async def test_study_frequency_does_not_follow_user_preferred_pose(client, database, tmp_path):
    study = (await client.post("/studies", json=design())).json()
    claim = await claim_next(database, "worker")
    report = minimal_report(tmp_path, claim.spec)
    record = report["records"][0]
    record["poses"][0]["asp86_contact"] = True
    alternative = copy.deepcopy(record["poses"][0])
    alternative.update(id="pose-alternative", asp86_contact=False)
    record["poses"].append(alternative)
    (tmp_path / "report.json").write_text(json.dumps(report))
    assert await ingest_report(database, claim, tmp_path, report, final=True)
    candidate = (await client.get(f"/experiments/{claim.experiment_id}/candidates")).json()[
        "items"
    ][0]
    other = next(p for p in candidate["poses"] if p["label"] == "pose-alternative")
    response = await client.patch(
        f"/experiments/{claim.experiment_id}/decisions/{candidate['id']}",
        json={"preferred_pose_id": other["id"]},
        headers={"If-Match": '"0"'},
    )
    assert response.status_code == 200
    result = (await client.get(f"/studies/{study['id']}")).json()
    assert result["candidates"][0]["contact_hit_runs"] == 1
    observed = next(o for o in result["candidates"][0]["observations"] if o["candidate_id"])
    assert observed["selected_pose_id"] == candidate["structureId"] != other["id"]
