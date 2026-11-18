"""Pose evidence and viewer objects derived from the same saved coordinates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

import numpy as np
import prolif as plf
from capychem.experiments.chemistry.identity import scaffold_query
from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, rdDepictor, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D

if TYPE_CHECKING:
    from posebusters import PoseBusters


class MoleculeProperties(TypedDict):
    smiles: str
    molecular_weight: float
    clogp: float
    rotatable_bonds: int
    formal_charge: int
    heavy_atoms: int


def properties(mol: Chem.Mol) -> MoleculeProperties:
    heavy = Chem.RemoveHs(mol)
    return {
        "smiles": Chem.MolToSmiles(heavy, isomericSmiles=True),
        "molecular_weight": float(Descriptors.MolWt(heavy)),
        "clogp": float(Crippen.MolLogP(heavy)),
        "rotatable_bonds": int(rdMolDescriptors.CalcNumRotatableBonds(heavy)),
        "formal_charge": int(Chem.GetFormalCharge(heavy)),
        "heavy_atoms": heavy.GetNumHeavyAtoms(),
    }


def state_identity(mol: Chem.Mol) -> tuple[str, str]:
    smiles: str = Chem.MolToSmiles(Chem.RemoveHs(mol), isomericSmiles=True)
    return "state-" + hashlib.sha256(smiles.encode()).hexdigest()[:20], smiles


def hydrogen_preparation(mol: Chem.Mol) -> dict[str, Any]:
    """Describe the saved explicit graph without moving or assessing hydrogens."""
    groups = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 8:
            continue
        hydrogens = [n for n in atom.GetNeighbors() if n.GetAtomicNum() == 1]
        heavy = [n for n in atom.GetNeighbors() if n.GetAtomicNum() != 1]
        if (
            len(hydrogens) == 1
            and len(heavy) == 1
            and heavy[0].GetAtomicNum() == 6
            and mol.GetBondBetweenAtoms(atom.GetIdx(), heavy[0].GetIdx()).GetBondType()
            == Chem.BondType.SINGLE
        ):
            groups.append(
                {
                    "oxygen_atom_index": atom.GetIdx(),
                    "hydrogen_atom_index": hydrogens[0].GetIdx(),
                    "carbon_atom_index": heavy[0].GetIdx(),
                }
            )
    return {
        "policy": "fixed_explicit_hydrogens",
        "method": "RDKit AddHs coordinate placement; fixed during contact assessment",
        "note": "Hydrogen positions and the declared neutral protonation state are fixed "
        "approximations. This workflow does not optimize hydrogen orientations against "
        "the receptor or model state populations across pH.",
        "orientation_optimized_against_receptor": False,
        "orientation_sensitivity_assessed": False,
        "oh_groups": groups,
        "warnings": [
            {
                "code": "oh_orientation_not_sampled",
                "message": "Contains an O–H group whose hydrogen orientation was placed "
                "without receptor-conditioned optimization. Donor contacts may depend "
                "on this orientation; sensitivity has not been assessed for this pose.",
            }
        ]
        if groups
        else [],
    }


def parent_mapping(mol: Chem.Mol, parent: Chem.Mol) -> tuple[int, ...]:
    heavy = Chem.RemoveHs(mol)
    choices: tuple[tuple[int, ...], ...] = heavy.GetSubstructMatches(
        scaffold_query(parent), useChirality=True, uniquify=False, maxMatches=1000
    )
    if not choices:
        raise ValueError("Prepared pose no longer contains the declared parent scaffold")
    if heavy.GetNumConformers():
        xyz = heavy.GetConformer().GetPositions()
        pxyz = parent.GetConformer().GetPositions()
        return min(choices, key=lambda m: float(np.sum((xyz[list(m)] - pxyz) ** 2)))
    return choices[0]


def inspect_pose(
    mol: Chem.Mol,
    parent: Chem.Mol,
    receptor: Chem.Mol,
    receptor_path: Path,
    buster: PoseBusters,
    fingerprint: plf.Fingerprint,
    ring_indices: Sequence[int],
) -> dict[str, Any]:
    checks = buster.bust(mol, mol_cond=str(receptor_path)).iloc[0]
    check_map = {
        str(key): None
        if value is None or (isinstance(value, float) and np.isnan(value))
        else bool(value)
        for key, value in checks.items()
    }
    failed = [key for key, value in check_map.items() if value is not True]
    heavy = Chem.RemoveHs(mol)
    xyz = heavy.GetConformer().GetPositions()
    pxyz = parent.GetConformer().GetPositions()
    mappings = heavy.GetSubstructMatches(
        scaffold_query(parent), useChirality=True, uniquify=False, maxMatches=1000
    )
    if not mappings:
        raise ValueError("Pose lost parent scaffold")
    drift = min(
        float(
            np.sqrt(
                np.mean(np.sum((xyz[np.array(m)[ring_indices]] - pxyz[ring_indices]) ** 2, axis=1))
            )
        )
        for m in mappings
    )
    raw = fingerprint.generate(
        plf.Molecule.from_rdkit(mol), plf.Molecule.from_rdkit(receptor), metadata=True
    )
    ligand_xyz = mol.GetConformer().GetPositions()
    protein_xyz = receptor.GetConformer().GetPositions()
    contacts: list[dict[str, Any]] = []
    hinge: set[tuple[str, str]] = set()
    for pair, types in raw.items():
        for kind, values in types.items():
            if str(pair[1]) in {"GLU81.A", "LEU83.A"}:
                hinge.add((str(pair[1]), kind))
            for value in values:
                li = int(value["parent_indices"]["ligand"][0])
                pi = int(value["parent_indices"]["protein"][0])
                distance = float(np.linalg.norm(ligand_xyz[li] - protein_xyz[pi]))
                if abs(distance - float(value["distance"])) > 0.001:
                    raise ValueError("Contact endpoints do not match distance evidence")
                info = receptor.GetAtomWithIdx(pi).GetPDBResidueInfo()
                contacts.append(
                    {
                        "type": kind,
                        "residue": str(pair[1]),
                        "chain": info.GetChainId(),
                        "residue_number": info.GetResidueNumber(),
                        "insertion_code": info.GetInsertionCode().strip(),
                        "protein_atom_name": info.GetName().strip(),
                        "ligand_atom_index": li,
                        "protein_atom_index": pi,
                        "ligand_position": ligand_xyz[li].tolist(),
                        "protein_position": protein_xyz[pi].tolist(),
                        "distance_A": distance,
                        "angle_degrees": float(value["DHA_angle"]),
                    }
                )
    asp = any(c["residue"] == "ASP86.A" for c in contacts)
    ready = not failed and drift <= 2.0 and len(hinge) >= 1
    return {
        "geometry_pass": not failed,
        "geometry_checks": check_map,
        "geometry_failures": failed,
        "ring_drift_A": drift,
        "hinge_hbond_type_count": len(hinge),
        "asp86_contact": asp,
        "contacts": contacts,
        "review_ready": ready,
        "hydrogen_preparation": hydrogen_preparation(mol),
    }


def write_sdf(
    mol: Chem.Mol,
    path: Path,
    name: str,
    coordinate_frame: str = "Original 1H1P receptor coordinates; angstrom",
) -> None:
    mol.SetProp("_Name", name)
    mol.SetProp("coordinate_frame", coordinate_frame)
    with Chem.SDWriter(str(path)) as writer:
        writer.write(mol)


def depiction(mol: Chem.Mol, path: Path) -> None:
    drawing = Chem.RemoveHs(Chem.Mol(mol))
    rdDepictor.Compute2DCoords(drawing)
    drawer = rdMolDraw2D.MolDraw2DSVG(500, 260)
    drawer.drawOptions().clearBackground = False
    drawer.drawOptions().padding = 0.08
    drawer.DrawMolecule(drawing)
    drawer.FinishDrawing()
    path.write_text(drawer.GetDrawingText())


def viewer_structure(
    mol: Chem.Mol,
    parent: Chem.Mol,
    receptor: Chem.Mol,
    preset: dict[str, Any],
    pose_id: str,
    compound: str,
    evidence: dict[str, Any],
    sdf: str,
    origin: str = "predicted",
) -> dict[str, Any]:
    """No ligand fit or hidden display transform: every artifact shares one frame."""
    heavy = Chem.RemoveHs(mol)
    state_id, smiles = state_identity(heavy)
    canonical = Chem.MolFromSmiles(smiles)
    canonical_to_pose = heavy.GetSubstructMatch(canonical, useChirality=True)
    if len(canonical_to_pose) != heavy.GetNumAtoms():
        raise ValueError("Cannot map the pose to its prepared-state atom identities")
    atom_ids = {
        pose_index: f"{state_id}:a{canonical_index}"
        for canonical_index, pose_index in enumerate(canonical_to_pose)
    }
    parent_names = json.loads(parent.GetProp("ccd_atom_names"))
    mapping = parent_mapping(heavy, parent)
    source_names = {target: parent_names[source] for source, target in enumerate(mapping)}
    ring_names = set(preset["scaffold"]["ring_atoms"])
    xyz = heavy.GetConformer().GetPositions()
    ligand_atoms = [
        {
            "id": atom_ids[i],
            "index": i,
            "name": source_names.get(i, f"{atom.GetSymbol()}{i}"),
            "element": atom.GetSymbol(),
            "position": xyz[i].tolist(),
            "scaffold": i in source_names,
            "purine": source_names.get(i) in ring_names,
            "attachment": source_names.get(i) == preset["scaffold"]["attachment_atom_name"],
            "extension": i not in source_names,
        }
        for i, atom in enumerate(heavy.GetAtoms())
    ]
    ligand_bonds = [
        {
            "a": atom_ids[b.GetBeginAtomIdx()],
            "b": atom_ids[b.GetEndAtomIdx()],
            "order": b.GetBondTypeAsDouble(),
            "aromatic": b.GetIsAromatic(),
        }
        for b in heavy.GetBonds()
    ]
    protein_xyz = receptor.GetConformer().GetPositions()
    pocket_keys = set()
    # Include whole residues within six angstrom and every reported contact.
    contact_indices = {c["protein_atom_index"] for c in evidence.get("contacts", [])}

    def residue_key(info: Chem.AtomPDBResidueInfo) -> tuple[str, int, str]:
        return (info.GetChainId(), info.GetResidueNumber(), info.GetInsertionCode().strip())

    for atom in receptor.GetAtoms():
        info = atom.GetPDBResidueInfo()
        if atom.GetAtomicNum() <= 1 or info is None:
            continue
        index = atom.GetIdx()
        if (
            index in contact_indices
            or float(np.linalg.norm(xyz - protein_xyz[index], axis=1).min()) <= 6
        ):
            pocket_keys.add(residue_key(info))
    pocket_atoms: list[dict[str, Any]] = []
    backbone_atoms: list[dict[str, Any]] = []
    protein_ids: dict[int, str] = {}
    by_index: dict[int, dict[str, Any]] = {}
    for atom in receptor.GetAtoms():
        info = atom.GetPDBResidueInfo()
        if atom.GetAtomicNum() <= 1 or info is None:
            continue
        chain, number, insertion = residue_key(info)
        name = info.GetName().strip()
        residue_id = f"{chain}:{number}{insertion}"
        identifier = (
            f"{preset['id']}:model1:asu:{chain}:{number}:{insertion or '.'}:"
            f"{info.GetResidueName().strip()}:{name}:{info.GetAltLoc().strip() or '.'}"
        )
        row = {
            "id": identifier,
            "index": atom.GetIdx(),
            "name": name,
            "element": atom.GetSymbol(),
            "residue": info.GetResidueName().strip(),
            "residueId": residue_id,
            "residueNumber": number,
            "chain": chain,
            "position": protein_xyz[atom.GetIdx()].tolist(),
        }
        if name == "CA":
            backbone_atoms.append(row)
        if residue_key(info) in pocket_keys:
            pocket_atoms.append(row)
            protein_ids[atom.GetIdx()] = identifier
            by_index[atom.GetIdx()] = row
    pocket_bonds = [
        {"a": protein_ids[b.GetBeginAtomIdx()], "b": protein_ids[b.GetEndAtomIdx()]}
        for b in receptor.GetBonds()
        if b.GetBeginAtomIdx() in protein_ids and b.GetEndAtomIdx() in protein_ids
    ]
    contacts = []
    for index, contact in enumerate(evidence.get("contacts", [])):
        protein = by_index[contact["protein_atom_index"]]
        contacts.append(
            {
                "id": f"{pose_id}:contact:{index}",
                "ligandAtom": atom_ids[contact["ligand_atom_index"]],
                "proteinAtom": protein["id"],
                "residueId": protein["residueId"],
                "residueLabel": f"{protein['residue'].title()}{protein['residueNumber']}",
                "kind": contact["type"],
                "distance": contact["distance_A"],
                "angle": contact["angle_degrees"],
                "provenance": "ProLIF on saved pose and prepared receptor; geometric evidence",
            }
        )
    return {
        "id": pose_id,
        "compound": compound,
        "component": preset.get("parent", {}).get("component", "CMG")
        if origin in {"observed", "template"}
        else "candidate",
        "origin": origin,
        "receptorId": preset["id"],
        "sourceUrl": preset.get("parent", {}).get("source_url", preset["source"]["url"])
        if origin in {"observed", "template"}
        else preset["source"]["url"],
        "coordinateNote": (
            preset.get("parent", {}).get("reference_label", "Observed parent") + "; "
            if origin in {"observed", "template"}
            else "Predicted pose; "
        )
        + f"original {preset['source']['pdb']} receptor frame; no ligand fitting",
        "referencePoseKind": preset.get("parent", {}).get("pose_kind", "observed")
        if origin in {"observed", "template"}
        else "predicted",
        "alignment": {
            "reference": preset["source"]["pdb"],
            "atomCount": 0,
            "method": "identity; common receptor frame",
            "backboneRmsd": 0,
        },
        "ligandAtoms": ligand_atoms,
        "ligandBonds": ligand_bonds,
        "pocketAtoms": pocket_atoms,
        "pocketBonds": pocket_bonds,
        "backboneAtoms": backbone_atoms,
        "contacts": contacts,
        "hydrogenPreparation": evidence.get("hydrogen_preparation"),
        "sdfUrl": sdf,
        "sdfCoordinateFrame": f"Original {preset['source']['pdb']} receptor coordinates; Å",
        "properties": properties(heavy),
        "atomMapping": {
            "preparedStateId": state_id,
            "canonicalToPose": list(canonical_to_pose),
            "parentToPose": list(mapping),
            "parentAtomNames": parent_names,
        },
    }
