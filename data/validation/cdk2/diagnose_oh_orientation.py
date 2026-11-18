#!/usr/bin/env python3
"""Read-only OH orientation sensitivity diagnostic on completed experiment poses.

This is not docking, receptor-conditioned hydrogen optimization, or a way to
select a new pose. It writes no structures and never changes an experiment.
Run using the isolated science Python after inference has completed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import prolif as plf
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms


def diagnose(directory: Path, names: set[str]) -> dict[str, Any]:
    report = json.loads((directory / "report.json").read_text())
    if report["status"] != "complete":
        raise ValueError("Only completed saved experiments can be diagnosed")
    receptor = Chem.MolFromPDBFile(
        str(directory / report["target"]["receptor_pdb"]), removeHs=False
    )
    protein = plf.Molecule.from_rdkit(receptor)
    fingerprint = plf.Fingerprint(interactions=["HBDonor", "HBAcceptor"])
    results = []
    for record in report["records"]:
        if record["name"] not in names:
            continue
        pose = next(p for p in record["poses"] if p["id"] == record["selected_pose_id"])
        original = Chem.SDMolSupplier(str(directory / pose["sdf"]), removeHs=False)[0]
        heavy = [a.GetIdx() for a in original.GetAtoms() if a.GetAtomicNum() != 1]
        for oxygen in original.GetAtoms():
            hydrogens = [n.GetIdx() for n in oxygen.GetNeighbors() if n.GetAtomicNum() == 1]
            neighbors = [n.GetIdx() for n in oxygen.GetNeighbors() if n.GetAtomicNum() != 1]
            if oxygen.GetAtomicNum() != 8 or len(hydrogens) != 1 or len(neighbors) != 1:
                continue
            oi, hi, ci = oxygen.GetIdx(), hydrogens[0], neighbors[0]
            upstream = [
                n.GetIdx()
                for n in original.GetAtomWithIdx(ci).GetNeighbors()
                if n.GetAtomicNum() != 1 and n.GetIdx() != oi
            ]
            if not upstream:
                continue
            entries = []
            # The grid is fixed independently of detected contacts or energies.
            for angle in [None, 0, 60, 120, 180, 240, 300]:
                molecule = Chem.Mol(original)
                if angle is not None:
                    rdMolTransforms.SetDihedralDeg(
                        molecule.GetConformer(), upstream[0], ci, oi, hi, angle
                    )
                xyz = molecule.GetConformer().GetPositions()
                displacement = float(
                    np.max(
                        np.linalg.norm(
                            xyz[heavy] - original.GetConformer().GetPositions()[heavy], axis=1
                        )
                    )
                )
                if displacement > 1e-8:
                    raise ValueError("Diagnostic unexpectedly moved heavy atoms")
                contacts = fingerprint.generate(
                    plf.Molecule.from_rdkit(molecule), protein, metadata=True
                )
                asp86 = [
                    {
                        "type": kind,
                        "distance_A": value["distance"],
                        "angle_degrees": value["DHA_angle"],
                        "ligand_atom_index": value["parent_indices"]["ligand"][0],
                        "protein_atom_index": value["parent_indices"]["protein"][0],
                    }
                    for pair, types in contacts.items()
                    if str(pair[1]) == "ASP86.A"
                    for kind, values in types.items()
                    for value in values
                ]
                properties = AllChem.MMFFGetMoleculeProperties(molecule, mmffVariant="MMFF94s")
                field = (
                    AllChem.MMFFGetMoleculeForceField(molecule, properties) if properties else None
                )
                entries.append(
                    {
                        "specified_OH_dihedral_degrees": angle,
                        "actual_dihedral_degrees": rdMolTransforms.GetDihedralDeg(
                            molecule.GetConformer(), upstream[0], ci, oi, hi
                        ),
                        "asp86_contacts": asp86,
                        "ligand_only_MMFF94s_energy_kcal_mol": (
                            field.CalcEnergy() if field else None
                        ),
                        "maximum_heavy_atom_displacement_A": displacement,
                    }
                )
            results.append(
                {
                    "candidate": record["name"],
                    "selected_pose_id": pose["id"],
                    "oxygen_atom_index": oi,
                    "baseline": entries[0],
                    "uniform_grid": entries[1:],
                }
            )
    return {
        "purpose": "Post-inference sensitivity diagnostic only: six fixed OH torsions, "
        "unchanged heavy atoms. No receptor-conditioned minimization or pose selection. "
        "Ligand-only MMFF energy is not binding energy. No coordinates are written or "
        "fed into inference. A possible contact does not establish that rotamer's population.",
        "report_directory": str(directory.resolve()),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-directory", type=Path, required=True)
    parser.add_argument("--candidate-name", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.report_directory, set(args.candidate_name))
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
