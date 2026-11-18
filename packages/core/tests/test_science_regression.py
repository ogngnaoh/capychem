"""Comparator tests use synthetic records, never claim molecular predictions."""

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capychem.experiments.science_regression import (
    contract_failures,
    digest,
    science_comparison,
)

ROOT = Path(__file__).resolve().parents[3]
POLICY = {"known_pose_rmsd_max_A": 2.0}


def fixture(generated=False):
    records = []
    for index, (name, smiles) in enumerate([("NU6094", "CC"), ("NU6102", "CCC")]):
        pose = {
            "id": f"pose-{index}",
            "score": -8.0,
            "prepared_smiles": smiles,
            "prepared_state_id": "state-" + hashlib.sha256(smiles.encode()).hexdigest()[:20],
            "review_ready": True,
            "geometry_pass": True,
            "asp86_contact": index == 1,
            "ring_drift_A": 0.4,
            "hinge_hbond_type_count": 2,
            "sdf": f"poses/pose-{index}.sdf",
        }
        records.append(
            {
                "id": f"candidate-{index}",
                "proposal_index": index,
                "name": name,
                "proposal_smiles": smiles,
                "normalized_smiles": smiles,
                "evaluated": True,
                "status": "ready_for_review",
                "poses": [pose],
                "selected_pose_id": pose["id"],
                "pose_errors": [],
            }
        )
    source = (
        {"kind": "libinvent", "raw_proposal_count": 2, "seed": 47}
        if generated
        else {
            "kind": "supplied",
            "candidates": [{"name": r["name"], "smiles": r["proposal_smiles"]} for r in records],
        }
    )
    spec = {
        "candidate_source": source,
        "protocol": "test-v2",
        "seeds": {"embedding": 1, "vina": 2},
        "limits": {"max_unique_candidates_evaluated": 6, "embedding_attempts_per_candidate": 16},
    }
    report = {
        "request_spec": {
            **spec,
            "resolved_protocol": {
                "engine_fingerprint": "engine",
                "target_manifest_sha256": "preparation",
                "revision": 2,
            },
        },
        "records": records,
        "raw_proposals": [{}, {}],
        "source_accounting": {"requested": 2, "returned": 2},
        "seconds": 10,
        "provenance": {"engine_fingerprint": "engine", "preset_sha256": "preparation"},
        "spec": copy.deepcopy(spec),
        "protocol_manifest": {
            "id": "test-v2",
            "version": 2,
            "vina": {"seed": 2},
            "embedding": {"seed_start": 1, "attempts": 16},
        },
        "generation": {"source": "libinvent", "seed": 47} if generated else None,
        "artifacts": [{"path": f"poses/pose-{i}.sdf", "sha256": f"hash-{i}"} for i in range(2)],
    }
    report["provenance"]["request_spec_sha256"] = digest(report["request_spec"])
    exported = project(report)
    case = {
        "spec": spec,
        "hard_expectations": []
        if generated
        else [{"proposal_index": i, "admission": "evaluated"} for i in range(2)],
        "scientific_controls": []
        if generated
        else [
            {
                "proposal_index": i,
                "name": r["name"],
                "geometry_pass": True,
                "review_ready": True,
                "asp86_contact": i == 1,
                "maximum_ring_drift_A": 2,
                "minimum_hinge_hbond_types": 1,
            }
            for i, r in enumerate(records)
        ],
        "reference_measurements": {
            "summary": copy.deepcopy(report["summary"]),
            "science_seconds": 10,
            "candidates": [
                {
                    "normalized_smiles": r["normalized_smiles"],
                    "selected": copy.deepcopy(r["poses"][0]),
                }
                for r in records
            ],
        },
    }
    return case, report, exported


def project(report):
    records = report["records"]
    selected = [
        next((p for p in r["poses"] if p["id"] == r["selected_pose_id"]), None) for r in records
    ]
    summary = {
        "raw_proposals": len(records),
        "processed_proposals": len(records),
        "unique_candidates": len({r["normalized_smiles"] for r in records}),
        "evaluated_candidates": sum(r["evaluated"] for r in records),
        "pose_count": sum(len(r["poses"]) for r in records),
        "pose_failures": 0,
        "objective_hits": sum(
            bool(p and p["review_ready"] and p["asp86_contact"]) for p in selected
        ),
    }
    report["summary"] = summary
    counts = {
        "proposals": summary["raw_proposals"],
        "pending": 0,
        "evaluated": summary["evaluated_candidates"],
        "poses": summary["pose_count"],
        "pose_errors": 0,
        "objective_hits": summary["objective_hits"],
        "review_ready": sum(bool(p and p["review_ready"]) for p in selected),
        "excluded": sum(
            r["status"] in {"duplicate", "outside_constraints", "invalid"} for r in records
        ),
        "deferred": 0,
        "active_attempt_id": "00000000-0000-0000-0000-000000000001",
    }
    candidates = []
    for r, p in zip(records, selected, strict=True):
        candidates.append(
            {
                "id": r["id"] + "-uuid",
                "attemptId": counts["active_attempt_id"],
                "sourceId": r["id"],
                "status": r["status"],
                "poseCount": len(r["poses"]),
                "duplicateOfSourceId": r.get("duplicate_of"),
                "duplicateOfCandidateId": r["duplicate_of"] + "-uuid"
                if r.get("duplicate_of")
                else None,
                "error": r.get("error"),
                "structureId": p["id"] if p else None,
                "score": p["score"] if p else None,
                "asp86Contact": p["asp86_contact"] if p else None,
                "reviewReady": p["review_ready"] if p else False,
                "poses": [
                    {
                        "id": p["id"],
                        "label": p["id"],
                        "preparedSmiles": p["prepared_smiles"],
                        "sdfUrl": "/artifacts/" + p["id"],
                    }
                ]
                if p
                else [],
            }
        )
    return {
        "experiment": {"spec": copy.deepcopy(report["request_spec"]), "counts": counts},
        "candidates": candidates,
        "artifacts": [
            {
                "attempt_id": counts["active_attempt_id"],
                "relative_path": a["path"],
                "sha256": a["sha256"],
                "url": "/artifacts/" + Path(a["path"]).stem,
            }
            for a in report["artifacts"]
        ],
    }


class RegressionComparatorTests(unittest.TestCase):
    def test_score_variation_is_descriptive_not_a_quality_failure(self):
        case, report, _ = fixture()
        report["records"][1]["poses"][0]["score"] -= 0.7
        self.assertEqual(contract_failures(case, report, project(report)), [])
        result = science_comparison(case, report, POLICY)
        self.assertEqual(result["status"], "pass")
        self.assertAlmostEqual(result["candidate_comparisons"][1]["score_delta"], -0.7)
        self.assertEqual(result["molecular_audit"], "not_run")

    def test_known_contact_loss_requires_scientific_review_not_contract_failure(self):
        case, report, _ = fixture()
        report["records"][1]["poses"][0]["asp86_contact"] = False
        self.assertEqual(contract_failures(case, report, project(report)), [])
        result = science_comparison(case, report, POLICY)
        self.assertEqual(result["status"], "review_required")
        self.assertIn("control:NU6102:asp86_contact_changed", result["review_reasons"])

    def test_geometry_and_heldout_rmsd_are_separate_scientific_controls(self):
        case, report, _ = fixture()
        report["records"][1]["poses"][0]["geometry_pass"] = False
        result = science_comparison(
            case, report, POLICY, {"selected_native_rmsd_A": {"candidate-1": 2.3}}
        )
        self.assertIn("control:NU6102:geometry_pass_changed", result["review_reasons"])
        self.assertIn("control:NU6102:heldout_pose_rmsd", result["review_reasons"])

    def test_new_generated_contact_is_not_a_regression(self):
        case, report, _ = fixture(generated=True)
        case["reference_measurements"]["summary"]["objective_hits"] = 0
        result = science_comparison(case, report, POLICY)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["summary_deltas"]["objective_hits"]["delta"], 1)
        self.assertEqual(contract_failures(case, report, project(report)), [])

    def test_new_study_has_no_invented_zero_reference_measurements(self):
        case, report, _ = fixture()
        case["reference_measurements"].update(summary=None, science_seconds=None)
        result = science_comparison(case, report, POLICY)
        self.assertIsNone(result["summary_deltas"]["objective_hits"]["baseline"])
        self.assertIsNone(result["summary_deltas"]["objective_hits"]["delta"])
        self.assertIsNone(result["science_seconds_delta"])

    def test_lost_raw_proposal_is_a_contract_failure(self):
        case, report, export = fixture()
        report["raw_proposals"].pop()
        self.assertIn("accounting:raw_proposals", contract_failures(case, report, export))

    def test_frozen_execution_seed_and_protocol_are_checked(self):
        case, report, export = fixture()
        report["spec"]["seeds"]["vina"] = 999
        report["protocol_manifest"]["id"] = "wrong"
        failures = contract_failures(case, report, export)
        self.assertIn("request:executable_spec_mismatch", failures)
        self.assertIn("protocol:identity", failures)

    def test_another_valid_sdf_cannot_be_substituted_for_selected_pose(self):
        case, report, export = fixture()
        export["candidates"][1]["poses"][0]["sdfUrl"] = "/artifacts/pose-0"
        self.assertIn("pose:pose-1:sdf_artifact_binding", contract_failures(case, report, export))

    def test_recovered_attempt_prefix_does_not_change_raw_identity(self):
        case, report, export = fixture()
        for row in export["candidates"]:
            row["sourceId"] = "00000000/" + row["sourceId"]
            for pose in row["poses"]:
                pose["label"] = "00000000/" + pose["label"]
        self.assertEqual(contract_failures(case, report, export), [])

    def test_generated_partial_execution_requires_review_even_without_control(self):
        case, report, _ = fixture(generated=True)
        report["execution_outcome"] = "completed_with_errors"
        report["records"][0]["embedding_attempts"] = [{"status": "failed"}]
        result = science_comparison(case, report, POLICY)
        self.assertEqual(result["status"], "review_required")
        self.assertIn("execution:candidate-0:incomplete_pose_pipeline", result["review_reasons"])

    def test_actual_generation_seed_cannot_differ_from_request(self):
        case, report, export = fixture(generated=True)
        report["generation"]["seed"] = 48
        self.assertIn("generation:seed", contract_failures(case, report, export))

    def test_selected_prepared_identity_mismatch_is_a_contract_failure(self):
        case, report, export = fixture()
        export["candidates"][1]["poses"][0]["preparedSmiles"] = "C"
        self.assertIn("pose:candidate-1:prepared_identity", contract_failures(case, report, export))

    def test_duplicate_link_must_match_the_normalized_original(self):
        case, report, _ = fixture()
        row = report["records"][1]
        row.update(
            status="duplicate",
            poses=[],
            selected_pose_id=None,
            evaluated=False,
            duplicate_of="candidate-0",
            normalized_smiles="CC",
        )
        case["hard_expectations"][1] = {
            "proposal_index": 1,
            "admission": "not_evaluated",
            "status": "duplicate",
            "duplicate_of_proposal_index": 0,
        }
        export = project(report)
        self.assertEqual(contract_failures(case, report, export), [])
        export["candidates"][1]["duplicateOfSourceId"] = None
        self.assertIn("duplicate:candidate-1:api_link", contract_failures(case, report, export))

    def test_fixture_keeps_generated_results_descriptive_and_reference_separate(self):
        baseline = json.loads(
            (ROOT / "data/validation/cdk2/growth-v2-baseline-v1.json").read_text()
        )
        generated = next(c for c in baseline["cases"] if c["id"] == "generated")
        self.assertEqual(generated["hard_expectations"], [])
        self.assertEqual(generated["scientific_controls"], [])
        for case in baseline["cases"]:
            self.assertNotIn("sdf", json.dumps(case["spec"]).lower())
            self.assertIsNone(case["spec"]["parent_experiment_id"])
        reference = ROOT / baseline["heldout_reference"]["path"]
        self.assertEqual(
            hashlib.sha256(reference.read_bytes()).hexdigest(),
            baseline["heldout_reference"]["sha256"],
        )

    def test_runner_is_opt_in_and_rejects_artifact_path_escape(self):
        spec = importlib.util.spec_from_file_location(
            "validate_science_api", ROOT / "scripts/validate_science_api.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(
            module.API, "read", side_effect=AssertionError("No network without --run")
        ):
            self.assertEqual(module.main([]), 0)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(module.ContractError):
            module.API("http://127.0.0.1:8002").download(
                {
                    "relative_path": "../other/report.json",
                    "attempt_id": "00000000-0000-0000-0000-000000000001",
                },
                Path(directory),
            )

    def test_renamed_generated_case_checks_runtime_before_submitting(self):
        spec = importlib.util.spec_from_file_location(
            "validate_science_api", ROOT / "scripts/validate_science_api.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        baseline = json.loads(
            (ROOT / "data/validation/cdk2/growth-v2-baseline-v1.json").read_text()
        )
        generated = next(c for c in baseline["cases"] if c["id"] == "generated")
        generated["id"] = "libinvent-alternate-seed"
        baseline["cases"] = [generated]
        identity = baseline["identity"]
        ready = {
            "ready": True,
            "capabilities": {"libinvent": False},
            "worker": {"health": {
                "science": {"versions": identity["science_versions"]},
                "generator": identity["generator"],
            }},
        }
        preset = {
            "id": identity["target_preparation_id"],
            "manifest": {"manifest_sha256": identity["target_manifest_sha256"]},
            "protocol_descriptor": {
                "id": identity["protocol"],
                "revision": identity["protocol_revision"],
                "engine_fingerprint": identity["engine_fingerprint"],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_path = root / "baseline.json"
            fixture_path.write_text(json.dumps(baseline))
            with patch.object(module.API, "read", side_effect=[ready, {"presets": [preset]}]), \
                 patch.object(module, "replay_case", side_effect=AssertionError("Must not submit")):
                self.assertEqual(module.main([
                    "--baseline", str(fixture_path), "--run", "--output-dir", str(root / "output")
                ]), 1)
            result = json.loads((root / "output/comparison.json").read_text())
            self.assertIn("ready LibInvent generator", result["error"])


if __name__ == "__main__":
    unittest.main()
