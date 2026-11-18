"""Contract edge cases and a real CPU artifact-integrity integration test.

The integration test is opt-in: CAPYCHEM_TEST_SCIENCE_PYTHON and
CAPYCHEM_VINA_BINARY point to explicitly installed tools. It never downloads.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from capychem.experiments.science import choose_pose, normalize_spec
from capychem.experiments.science_config import (
    MAX_RANDOM_SEED,
    MAX_SMILES_LENGTH,
    canonical_json_sha256,
    engine_fingerprint,
    load_preset,
    protocol_descriptor,
)


class ScienceContractTests(unittest.TestCase):
    def test_selection_does_not_hide_failed_geometry_behind_good_score(self):
        poses = [
            {"id": "invalid", "review_ready": False, "asp86_contact": True, "score": -20},
            {"id": "eligible", "review_ready": True, "asp86_contact": False, "score": -9},
            {"id": "target", "review_ready": True, "asp86_contact": True, "score": -7},
        ]
        self.assertEqual(choose_pose(poses)["id"], "target")
        self.assertEqual(choose_pose(poses[:2])["id"], "eligible")
        self.assertEqual(choose_pose(poses[:1])["id"], "invalid")
        self.assertIsNone(choose_pose([]))

    def test_unsupported_targets_and_fractional_attempts_are_rejected(self):
        base = {"candidate_source": {"kind": "supplied", "candidates": [{"smiles": "CCO"}]}}
        for change in [
            {"target_preparation_id": "anything"},
            {"limits": {"embedding_attempts_per_candidate": 1.5}},
            {"seeds": {"embedding": -1}},
            {"constraints": {"formal_charge": 1}},
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_spec({**base, **change})

    def test_preset_is_verified_and_declares_source_identity(self):
        preset = load_preset()
        self.assertEqual(preset["source"]["ligand"]["author_residue_number"], 1298)
        self.assertEqual(preset["scaffold"]["attachment_atom_name"], "N2")
        self.assertEqual(len(preset["reference_candidates"]), 4)

    def test_protocol_descriptor_freezes_implementation_without_chemistry_imports(self):
        descriptor = protocol_descriptor("guided_local_cdk2_v1")
        self.assertEqual(descriptor["revision"], 1)
        self.assertEqual(descriptor["engine_fingerprint"], engine_fingerprint())
        self.assertEqual(
            descriptor["engine_fingerprint"],
            canonical_json_sha256(descriptor["implementation_sha256"]),
        )
        with self.assertRaises(ValueError):
            protocol_descriptor("unknown")

    def test_growth_preset_declares_scaffold_and_held_out_target_coordinates(self):
        preset = load_preset("cdk2_1h1s_nu6094_v1")
        spec = normalize_spec(preset["default_spec"])
        self.assertEqual(spec["protocol"], "guided_growth_cdk2_v2")
        self.assertEqual(spec["limits"]["embedding_attempts_per_candidate"], 16)
        self.assertEqual(preset["scaffold"]["retained_heavy_atoms"], 24)
        self.assertEqual(preset["scaffold"]["attachment_atom_name"], "C20")
        self.assertNotIn("1H1S_native.sdf", preset["files"].values())
        self.assertFalse(preset["validation_scope"]["target_ligand_coordinates_used_for_placement"])
        with self.assertRaises(ValueError):
            normalize_spec({**preset["default_spec"], "target_preparation_id": "cdk2_1h1p"})

    def test_public_contract_boundaries_reach_the_science_engine(self):
        for seed, weight, clogp, rotors in [
            (0, 100, -5, 0),
            (MAX_RANDOM_SEED, 1000, 10, 30),
        ]:
            with self.subTest(seed=seed, weight=weight, clogp=clogp, rotors=rotors):
                normalized = normalize_spec(
                    {
                        "candidate_source": {
                            "kind": "libinvent",
                            "raw_proposal_count": 128,
                            "seed": seed,
                        },
                        "seeds": {"embedding": seed, "vina": seed},
                        "constraints": {
                            "max_molecular_weight": weight,
                            "max_clogp": clogp,
                            "max_rotatable_bonds": rotors,
                            "formal_charge": 0,
                        },
                    }
                )
                self.assertEqual(normalized["constraints"]["max_clogp"], clogp)
                self.assertEqual(normalized["seeds"]["embedding"], seed)
        # Parsing validity is recorded during execution, not contract validation.
        normalized = normalize_spec(
            {
                "candidate_source": {
                    "kind": "supplied",
                    "candidates": [{"smiles": "C" * MAX_SMILES_LENGTH}],
                }
            }
        )
        self.assertEqual(
            len(normalized["candidate_source"]["candidates"][0]["smiles"]), MAX_SMILES_LENGTH
        )

    def test_out_of_contract_numbers_fail_before_execution(self):
        base = {"candidate_source": {"kind": "supplied", "candidates": [{"smiles": "CCO"}]}}
        invalid = [
            {"seeds": {"embedding": MAX_RANDOM_SEED + 1}},
            {"seeds": {"vina": True}},
            {"candidate_source": {"kind": "libinvent", "seed": MAX_RANDOM_SEED + 1}},
            {"candidate_source": {"kind": "libinvent", "raw_proposal_count": 2.5}},
            {"candidate_source": {"kind": "libinvent", "raw_proposal_count": True}},
            {
                "candidate_source": {
                    "kind": "supplied",
                    "candidates": [{"smiles": "C" * (MAX_SMILES_LENGTH + 1)}],
                }
            },
        ]
        for key, values in {
            "max_molecular_weight": [99, 1001, float("nan"), float("inf"), True],
            "max_clogp": [-5.1, 10.1, float("nan"), float("inf"), False],
            "max_rotatable_bonds": [-1, 31, 1.5, False],
            "formal_charge": [-1, 1, False],
        }.items():
            invalid.extend({"constraints": {key: value}} for value in values)
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_spec({**base, **change})


@unittest.skipUnless(
    os.environ.get("CAPYCHEM_TEST_SCIENCE_PYTHON") and os.environ.get("CAPYCHEM_VINA_BINARY"),
    "Real science test needs an explicit isolated science Python and Vina",
)
class RealScienceTests(unittest.TestCase):
    def test_hydrogen_warning_uses_saved_graph_without_moving_atoms(self):
        code = """
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from capychem.experiments.chemistry.geometry import hydrogen_preparation
for smiles, expected in [('Oc1ccccc1',1),('CCO',1),('COC',0),('CC(N)=O',0),('OCCO',2)]:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=43) == 0
    before = mol.GetConformer().GetPositions().copy()
    metadata = hydrogen_preparation(mol)
    assert len(metadata['oh_groups']) == expected
    assert bool(metadata['warnings']) == bool(expected)
    assert metadata['orientation_sensitivity_assessed'] is False
    assert metadata['orientation_optimized_against_receptor'] is False
    for group in metadata['oh_groups']:
        assert [mol.GetAtomWithIdx(group[k]).GetSymbol() for k in
                ['oxygen_atom_index','hydrogen_atom_index','carbon_atom_index']] == ['O','H','C']
    assert np.array_equal(before, mol.GetConformer().GetPositions())
"""
        process = subprocess.run(
            [os.environ["CAPYCHEM_TEST_SCIENCE_PYTHON"], "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_growth_control_recovers_contact_and_rejects_outside_scope_inputs(self):
        preset = load_preset("cdk2_1h1s_nu6094_v1")
        legacy = load_preset()
        spec = json.loads(json.dumps(preset["default_spec"]))
        for index in [0, 2]:
            candidate = legacy["reference_candidates"][index]
            spec["candidate_source"]["candidates"].append(
                {"name": candidate["name"], "smiles": candidate["smiles"]}
            )
        with tempfile.TemporaryDirectory(prefix="capychem-growth-test-") as directory:
            root = Path(directory)
            request = root / "input.json"
            request.write_text(json.dumps(spec))
            result = subprocess.run(
                [
                    os.environ["CAPYCHEM_TEST_SCIENCE_PYTHON"],
                    "-m",
                    "capychem.experiments.science",
                    "--input",
                    str(request),
                    "--output-dir",
                    str(root / "run"),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / "run/report.json").read_text())
            self.assertEqual(report["parent"]["name"], "NU6094")
            self.assertEqual(report["parent"]["pose_kind"], "protein_aligned_template")
            self.assertEqual(report["summary"]["objective_hits"], 1)
            control = report["records"][1]
            selected = next(p for p in control["poses"] if p["id"] == control["selected_pose_id"])
            self.assertTrue(selected["review_ready"] and selected["asp86_contact"])
            self.assertIn("parent_scaffold_not_retained", report["records"][2]["filter_failures"])
            self.assertIn(
                "modification_outside_declared_para_attachment",
                report["records"][3]["filter_failures"],
            )
            view = json.loads((root / "run" / report["parent"]["view_json"]).read_text())
            self.assertEqual(view["origin"], "template")
            self.assertEqual(sum(a["scaffold"] for a in view["ligandAtoms"]), 24)
            self.assertEqual([a["name"] for a in view["ligandAtoms"] if a["attachment"]], ["C20"])

    def test_real_run_keeps_failed_inputs_and_exports_consistent_evidence(self):
        preset = load_preset()
        parent = preset["reference_candidates"][0]
        candidates = [
            parent,
            {"name": "duplicate", "smiles": parent["smiles"]},
            {"name": "invalid", "smiles": "not-a-smiles"},
            {"name": "wrong scaffold", "smiles": "CCO"},
            preset["reference_candidates"][1],
            {
                "name": "alternative 7H tautomer of NU6094",
                "smiles": "c1ccc(Nc2nc(OCC3CCCCC3)c3[nH]cnc3n2)cc1",
            },
        ]
        spec = {
            "candidate_source": {"kind": "supplied", "candidates": candidates},
            "limits": {"max_unique_candidates_evaluated": 1, "embedding_attempts_per_candidate": 2},
            "parent_experiment_id": "preserve-the-request",
            "resolved_protocol": protocol_descriptor("guided_local_cdk2_v1"),
        }
        with tempfile.TemporaryDirectory(prefix="capychem-science-test-") as temporary:
            root = Path(temporary)
            request = root / "input.json"
            request.write_text(json.dumps(spec))
            output = root / "run"
            output.mkdir()
            for filename in ["input.json", "progress.jsonl", "stderr.log"]:
                (output / filename).write_text("worker-owned, still mutable\n")
            result = subprocess.run(
                [
                    os.environ["CAPYCHEM_TEST_SCIENCE_PYTHON"],
                    "-m",
                    "capychem.experiments.science",
                    "--input",
                    str(request),
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            events = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(events[-1]["type"], "experiment.complete")
            report = json.loads((output / "report.json").read_text())
            artifact_paths = {a["path"] for a in report["artifacts"]}
            self.assertTrue(
                artifact_paths.isdisjoint({"input.json", "progress.jsonl", "stderr.log"})
            )
            self.assertEqual(report["request_spec"], spec)
            self.assertEqual(
                report["provenance"]["request_spec_sha256"], canonical_json_sha256(spec)
            )
            self.assertEqual(
                report["provenance"]["engine_fingerprint"],
                spec["resolved_protocol"]["engine_fingerprint"],
            )
            self.assertEqual(
                [r["status"] for r in report["records"]],
                [
                    "ready_for_review",
                    "duplicate",
                    "invalid",
                    "outside_constraints",
                    "deferred_budget",
                    "duplicate",
                ],
            )
            self.assertEqual(report["summary"]["objective_hits"], 0)
            alternative, normalized = report["records"][5], report["records"][4]
            self.assertNotEqual(alternative["canonical_smiles"], normalized["canonical_smiles"])
            self.assertEqual(alternative["normalized_smiles"], normalized["normalized_smiles"])
            self.assertEqual(alternative["duplicate_of"], normalized["id"])
            self.assertTrue(alternative["preparation_transformations"])
            self.assertEqual(report["records"][1]["duplicate_of"], report["records"][0]["id"])
            poses = [report["parent"]["baseline_pose"], *report["records"][0]["poses"]]
            for pose in poses:
                view = json.loads((output / pose["view_json"]).read_text())
                self.assertEqual(view["hydrogenPreparation"], pose["hydrogen_preparation"])
                self.assertFalse(pose["hydrogen_preparation"]["orientation_sensitivity_assessed"])
                self.assertEqual(sum(a["scaffold"] for a in view["ligandAtoms"]), 18)
                self.assertEqual(sum(a["attachment"] for a in view["ligandAtoms"]), 1)
                self.assertEqual(sum(a["purine"] for a in view["ligandAtoms"]), 9)
                self.assertTrue((output / pose["sdf"]).is_file())
                by_id = {a["id"]: a for a in [*view["ligandAtoms"], *view["pocketAtoms"]]}
                for contact in view["contacts"]:
                    a, b = by_id[contact["ligandAtom"]], by_id[contact["proteinAtom"]]
                    distance = (
                        sum((x - y) ** 2 for x, y in zip(a["position"], b["position"], strict=True))
                        ** 0.5
                    )
                    self.assertAlmostEqual(distance, contact["distance"], places=5)
            # Reusing an attempt directory must not overwrite scientific artifacts.
            duplicate = subprocess.run(
                [
                    os.environ["CAPYCHEM_TEST_SCIENCE_PYTHON"],
                    "-m",
                    "capychem.experiments.science",
                    "--input",
                    str(request),
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(duplicate.returncode, 0)

            # Recomputing contacts must detect missing labels and invented
            # eligibility evidence even when saved geometry stays unchanged.
            audit_command = [
                os.environ["CAPYCHEM_TEST_SCIENCE_PYTHON"],
                "-m",
                "capychem.experiments.science_audit",
                "--output-dir",
                str(output),
            ]
            verified = subprocess.run(audit_command, capture_output=True, text=True, timeout=120)
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertEqual(json.loads(verified.stdout)["contact_set_rechecks"], len(poses))
            altered = report["records"][0]["poses"][0]
            self.assertTrue(altered["contacts"])
            altered["contacts"].pop()
            altered["ring_drift_A"] += 0.3
            altered["hinge_hbond_type_count"] += 1
            altered["asp86_contact"] = not altered["asp86_contact"]
            altered["hydrogen_preparation"]["orientation_sensitivity_assessed"] = True
            altered["hydrogen_preparation"]["oh_groups"] = [
                {"oxygen_atom_index": 0, "hydrogen_atom_index": 1, "carbon_atom_index": 2}
            ]
            (output / "report.json").write_text(json.dumps(report))
            rejected = subprocess.run(audit_command, capture_output=True, text=True, timeout=120)
            self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
            failures = json.loads(rejected.stdout)["failures"]
            for kind in [
                "contact_set_recheck",
                "ring_drift_recheck",
                "hinge_recheck",
                "asp86_recheck",
                "hydrogen_assessment_claim",
                "hydrogen_graph_warning",
            ]:
                self.assertIn(f"{kind}:{altered['id']}", failures)

            # A strict but valid property brief may exclude every candidate; it
            # must complete with evidence rather than fail at normalization.
            strict_request = root / "zero-limits.json"
            strict_request.write_text(
                json.dumps(
                    {
                        "candidate_source": {"kind": "supplied", "candidates": [parent]},
                        "constraints": {"max_clogp": 0, "max_rotatable_bonds": 0},
                    }
                )
            )
            strict_output = root / "zero-limits"
            strict_result = subprocess.run(
                [
                    os.environ["CAPYCHEM_TEST_SCIENCE_PYTHON"],
                    "-m",
                    "capychem.experiments.science",
                    "--input",
                    str(strict_request),
                    "--output-dir",
                    str(strict_output),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(strict_result.returncode, 0, strict_result.stderr)
            strict_report = json.loads((strict_output / "report.json").read_text())
            self.assertEqual(strict_report["status"], "complete")
            self.assertEqual(strict_report["records"][0]["status"], "outside_constraints")
            self.assertEqual(strict_report["summary"]["evaluated_candidates"], 0)
            self.assertEqual(strict_report["objective_outcome"], "not_assessed")


if __name__ == "__main__":
    unittest.main()
