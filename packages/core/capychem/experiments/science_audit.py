"""Independently check graph, stereo, coordinates and accounting in a live run.

Run in the science environment:
python -m capychem.experiments.science_audit --output-dir /path/to/run
This reads artifacts only and prints a JSON audit; it never changes the run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from capychem.experiments.science import choose_pose
from capychem.experiments.science_config import sha256


def audit(directory: Path) -> dict[str, Any]:
    import numpy as np
    import prolif as plf
    from capychem.experiments.chemistry.identity import scaffold_query
    from posebusters import PoseBusters
    from rdkit import Chem

    directory = directory.resolve()
    report = json.loads((directory / "report.json").read_text())
    failures: list[str] = []
    poses_checked = contacts_checked = geometry_checked = 0
    maximum_distance_error = 0.0
    receptor = Chem.MolFromPDBFile(
        str(directory / report["target"]["receptor_pdb"]), removeHs=False
    )
    protein_xyz = receptor.GetConformer().GetPositions()
    parent = Chem.SDMolSupplier(str(directory / report["parent"]["observed_sdf"]), removeHs=True)[0]
    parent_names = json.loads(parent.GetProp("ccd_atom_names"))
    ring_names = set(report["protocol_manifest"]["scaffold"]["ring_atoms"])
    retained_atoms = report["protocol_manifest"]["scaffold"]["retained_heavy_atoms"]
    attachment_name = report["protocol_manifest"]["scaffold"]["attachment_atom_name"]
    buster = PoseBusters(config="dock")
    fingerprint = plf.Fingerprint(interactions=report["protocol_manifest"]["contact_types"])
    contact_protein = plf.Molecule.from_rdkit(receptor)
    ring_indices = [i for i, name in enumerate(parent_names) if name in ring_names]
    parent_xyz = parent.GetConformer().GetPositions()
    contact_rechecks = 0
    by_id = {record["id"]: record for record in report["records"]}

    def check(condition: object, label: str) -> None:
        if not condition:
            failures.append(label)

    check(report["status"] == "complete", "experiment_not_complete")
    check(
        len(report["records"]) == report["source_accounting"]["returned"], "raw_proposal_accounting"
    )
    for artifact in report.get("artifacts", []):
        path = (directory / artifact["path"]).resolve()
        check(path.is_relative_to(directory), "artifact_path_outside_attempt")
        if path.is_relative_to(directory):
            check(
                path.is_file() and sha256(path) == artifact["sha256"],
                f"artifact_hash:{artifact['path']}",
            )
    records = [
        {
            "id": "parent",
            "normalized_smiles": report["parent"]["smiles"],
            "poses": [report["parent"]["baseline_pose"]],
        },
        *report["records"],
    ]
    for record in records:
        proposal = Chem.MolFromSmiles(record.get("normalized_smiles") or "")
        if record.get("status") == "duplicate":
            original = by_id.get(record.get("duplicate_of"))
            check(
                original is not None
                and original["normalized_smiles"] == record["normalized_smiles"],
                f"duplicate_identity:{record['id']}",
            )
        if record.get("evaluated"):
            if record.get("status") != "evaluation_error":
                check(
                    len(record["embedding_attempts"])
                    == report["spec"]["limits"]["embedding_attempts_per_candidate"],
                    f"embedding_attempt_accounting:{record['id']}",
                )
            generated = sum(a["status"] == "generated" for a in record["embedding_attempts"])
            check(
                generated == len(record["poses"]) + len(record["pose_errors"]),
                f"conformer_accounting:{record['id']}",
            )
            selected = choose_pose(record["poses"])
            check(
                record["selected_pose_id"] == (selected["id"] if selected else None),
                f"selection_policy:{record['id']}",
            )
            for error in record.get("pose_errors", []):
                check(record["partial"], f"partial_error_status:{record['id']}")
                if error["kind"] == "outside_grid":
                    error_log = directory / error["log"]
                    check(
                        error_log.is_file() and "outside the grid box" in error_log.read_text(),
                        f"outside_grid_error_log:{error['id']}",
                    )
        prepared = {state["id"]: state for state in record.get("prepared_states", [])}
        for pose in record.get("poses", []):
            poses_checked += 1
            mol = Chem.SDMolSupplier(str(directory / pose["sdf"]), removeHs=False)[0]
            check(mol is not None, f"unreadable_sdf:{pose['id']}")
            if mol is None:
                continue
            heavy = Chem.RemoveHs(mol)
            smiles = Chem.MolToSmiles(heavy, isomericSmiles=True)
            check(smiles == pose["prepared_smiles"], f"prepared_state_smiles:{pose['id']}")
            check(
                pose["prepared_state_id"]
                == "state-" + hashlib.sha256(smiles.encode()).hexdigest()[:20],
                f"prepared_state_hash:{pose['id']}",
            )
            check(
                heavy.HasSubstructMatch(proposal, useChirality=True),
                f"proposal_stereo:{pose['id']}",
            )
            check(
                heavy.GetNumAtoms() == proposal.GetNumAtoms(), f"proposal_atom_count:{pose['id']}"
            )
            if prepared:
                state = prepared.get(pose["prepared_state_id"])
                check(
                    state is not None and state["smiles"] == smiles,
                    f"prepared_state_link:{pose['id']}",
                )
            xyz = mol.GetConformer().GetPositions()
            check(bool(np.isfinite(xyz).all()), f"nonfinite_coordinates:{pose['id']}")
            view = json.loads((directory / pose["view_json"]).read_text())
            check(view["properties"]["smiles"] == smiles, f"viewer_graph:{pose['id']}")
            preparation = pose.get("hydrogen_preparation")
            if preparation is not None:
                check(
                    view.get("hydrogenPreparation") == preparation,
                    f"viewer_hydrogen_preparation:{pose['id']}",
                )
                expected_oh = set()
                for atom in mol.GetAtoms():
                    hydrogens = [n for n in atom.GetNeighbors() if n.GetAtomicNum() == 1]
                    carbons = [n for n in atom.GetNeighbors() if n.GetAtomicNum() == 6]
                    if (
                        atom.GetAtomicNum() == 8
                        and atom.GetDegree() == 2
                        and len(hydrogens) == 1
                        and len(carbons) == 1
                        and mol.GetBondBetweenAtoms(atom.GetIdx(), carbons[0].GetIdx())
                        .GetBondType()
                        == Chem.BondType.SINGLE
                    ):
                        expected_oh.add(
                            (atom.GetIdx(), hydrogens[0].GetIdx(), carbons[0].GetIdx())
                        )
                recorded_oh = {
                    (g["oxygen_atom_index"], g["hydrogen_atom_index"], g["carbon_atom_index"])
                    for g in preparation["oh_groups"]
                }
                check(
                    expected_oh == recorded_oh
                    and len(recorded_oh) == len(preparation["oh_groups"])
                    and bool(preparation["warnings"]) == bool(expected_oh),
                    f"hydrogen_graph_warning:{pose['id']}",
                )
                check(
                    preparation["orientation_sensitivity_assessed"] is False
                    and preparation["orientation_optimized_against_receptor"] is False,
                    f"hydrogen_assessment_claim:{pose['id']}",
                )
            check(
                sum(a["scaffold"] for a in view["ligandAtoms"]) == retained_atoms,
                f"viewer_scaffold:{pose['id']}",
            )
            check(sum(a["purine"] for a in view["ligandAtoms"]) == 9, f"viewer_ring:{pose['id']}")
            check(
                sum(a["attachment"] for a in view["ligandAtoms"]) == 1,
                f"viewer_attachment:{pose['id']}",
            )
            mapped = tuple(view["atomMapping"]["parentToPose"])
            check(
                mapped
                in heavy.GetSubstructMatches(
                    scaffold_query(parent), useChirality=True, uniquify=False, maxMatches=1000
                ),
                f"parent_atom_mapping:{pose['id']}",
            )
            canonical = Chem.MolFromSmiles(smiles)
            canonical_mapping = tuple(view["atomMapping"]["canonicalToPose"])
            check(
                canonical_mapping
                in heavy.GetSubstructMatches(
                    canonical, useChirality=True, uniquify=False, maxMatches=1000
                ),
                f"canonical_atom_mapping:{pose['id']}",
            )
            expected_ring = {
                mapped[index] for index, name in enumerate(parent_names) if name in ring_names
            }
            check(
                {atom["index"] for atom in view["ligandAtoms"] if atom["scaffold"]} == set(mapped),
                f"exact_scaffold_flags:{pose['id']}",
            )
            check(
                {atom["index"] for atom in view["ligandAtoms"] if atom["purine"]} == expected_ring,
                f"exact_ring_flags:{pose['id']}",
            )
            check(
                {atom["index"] for atom in view["ligandAtoms"] if atom["attachment"]}
                == {mapped[parent_names.index(attachment_name)]},
                f"exact_attachment_flag:{pose['id']}",
            )
            for atom in view["ligandAtoms"]:
                check(
                    float(np.linalg.norm(xyz[atom["index"]] - atom["position"])) < 1e-7,
                    f"viewer_coordinates:{pose['id']}:{atom['index']}",
                )
            atoms_by_id = {
                atom["id"]: atom for atom in [*view["ligandAtoms"], *view["pocketAtoms"]]
            }
            check(
                len(atoms_by_id) == len(view["ligandAtoms"]) + len(view["pocketAtoms"]),
                f"unique_atom_identities:{pose['id']}",
            )
            for contact in pose["contacts"]:
                contacts_checked += 1
                li, pi = contact["ligand_atom_index"], contact["protein_atom_index"]
                distance = float(np.linalg.norm(xyz[li] - protein_xyz[pi]))
                maximum_distance_error = max(
                    maximum_distance_error, abs(distance - contact["distance_A"])
                )
                check(
                    abs(distance - contact["distance_A"]) < 1e-5, f"contact_distance:{pose['id']}"
                )
            for contact in view["contacts"]:
                a = np.array(atoms_by_id[contact["ligandAtom"]]["position"])
                b = np.array(atoms_by_id[contact["proteinAtom"]]["position"])
                check(
                    abs(float(np.linalg.norm(a - b)) - contact["distance"]) < 1e-5,
                    f"viewer_contact_distance:{pose['id']}",
                )
            log = (directory / pose["log"]).read_text()
            match = re.search(
                r"(?:Affinity|Estimated Free Energy of Binding)\s*:\s*([-+\d.]+)", log
            )
            check(match is not None and float(match[1]) == pose["score"], f"score_log:{pose['id']}")
            checks = buster.bust(
                mol, mol_cond=str(directory / report["target"]["receptor_pdb"])
            ).iloc[0]
            fresh_geometry_pass = all(
                value is not None
                and not (isinstance(value, float) and np.isnan(value))
                and bool(value)
                for value in checks
            )
            check(
                fresh_geometry_pass == pose["geometry_pass"],
                f"geometry_recheck:{pose['id']}",
            )
            geometry_checked += 1
            # Recreate the complete interaction set, not only the distances of
            # contacts that happened to have been recorded by the engine.
            raw_contacts = fingerprint.generate(
                plf.Molecule.from_rdkit(mol), contact_protein, metadata=True
            )
            recalculated = []
            hinge = set()
            for pair, types in raw_contacts.items():
                residue = str(pair[1])
                for kind, values in types.items():
                    if residue in report["protocol_manifest"]["review"]["hinge_residues"]:
                        hinge.add((residue, kind))
                    for value in values:
                        recalculated.append(
                            (
                                kind,
                                residue,
                                int(value["parent_indices"]["ligand"][0]),
                                int(value["parent_indices"]["protein"][0]),
                                round(float(value["distance"]), 5),
                                round(float(value["DHA_angle"]), 5),
                            )
                        )
            recorded = [
                (
                    c["type"],
                    c["residue"],
                    c["ligand_atom_index"],
                    c["protein_atom_index"],
                    round(c["distance_A"], 5),
                    round(c["angle_degrees"], 5),
                )
                for c in pose["contacts"]
            ]
            check(Counter(recorded) == Counter(recalculated), f"contact_set_recheck:{pose['id']}")
            check(len(hinge) == pose["hinge_hbond_type_count"], f"hinge_recheck:{pose['id']}")
            asp = any(c[1] == "ASP86.A" for c in recalculated)
            check(asp == pose["asp86_contact"], f"asp86_recheck:{pose['id']}")
            heavy_xyz = heavy.GetConformer().GetPositions()
            mappings = heavy.GetSubstructMatches(
                scaffold_query(parent), useChirality=True, uniquify=False, maxMatches=1000
            )
            drift = min(
                float(
                    np.sqrt(
                        np.mean(
                            np.sum(
                                (
                                    heavy_xyz[np.asarray(mapping)[ring_indices]]
                                    - parent_xyz[ring_indices]
                                )
                                ** 2,
                                axis=1,
                            )
                        )
                    )
                )
                for mapping in mappings
            )
            check(abs(drift - pose["ring_drift_A"]) < 1e-6, f"ring_drift_recheck:{pose['id']}")
            review = report["protocol_manifest"]["review"]
            eligible = (
                fresh_geometry_pass
                and drift <= review["ring_drift_max_A"]
                and len(hinge) >= review["minimum_hinge_interaction_types"]
            )
            check(eligible == pose["review_ready"], f"eligibility_recheck:{pose['id']}")
            contact_rechecks += 1
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "raw_proposals": len(report["records"]),
        "poses_checked": poses_checked,
        "geometry_rechecks": geometry_checked,
        "contact_set_rechecks": contact_rechecks,
        "eligibility_rechecks": contact_rechecks,
        "contacts_checked": contacts_checked,
        "max_contact_distance_error_A": maximum_distance_error,
        "report_sha256": sha256(directory / "report.json"),
        "scope": "Artifact identity and computational consistency; "
        "not predictive accuracy or affinity validation",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.output_dir)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
