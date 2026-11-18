"""Reproduce the immutable NU6094/open-CDK2 preparation from prepared source files.

The NU6102 ligand is never read. Only its ligand-free 1H1S receptor is used.
Inputs: 1H1Q_native.sdf, 1H1Q_prepared.pdb, 1H1S_prepared.pdb/.pdbqt.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from capychem.experiments.science_config import GROWTH_PREPARATION_ID, sha256
from numpy.typing import NDArray
from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize

PARENT_SMILES = "c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1"
POSITIVE_SMILES = "NS(=O)(=O)c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1"


def backbone(receptor: Chem.Mol) -> dict[tuple[str, int, str, str], NDArray[np.float64]]:
    xyz: NDArray[np.float64] = receptor.GetConformer().GetPositions()
    return {
        (i.GetChainId(), i.GetResidueNumber(), i.GetInsertionCode(), i.GetName().strip()): xyz[
            a.GetIdx()
        ]
        for a in receptor.GetAtoms()
        if (i := a.GetPDBResidueInfo()) is not None
        and i.GetChainId() == "A"
        and i.GetName().strip() in {"N", "CA", "C", "O"}
    }


def prepare(source: Path, destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    names = ["1H1Q_native.sdf", "1H1Q_prepared.pdb", "1H1S_prepared.pdb", "1H1S_prepared.pdbqt"]
    for name in names:
        shutil.copyfile(source / name, destination / name)
    original = Chem.SDMolSupplier(str(destination / "1H1Q_native.sdf"), removeHs=True)[0]
    desired = Chem.MolToSmiles(Chem.MolFromSmiles(PARENT_SMILES))
    states = [
        m
        for m in rdMolStandardize.TautomerEnumerator().Enumerate(original)
        if Chem.MolToSmiles(m) == desired
    ]
    if len(states) != 1:
        raise ValueError("The source does not yield one declared neutral-9H NU6094 state")
    parent = states[0]
    parent.SetProp("ccd_atom_names", original.GetProp("ccd_atom_names"))
    if parent.GetNumHeavyAtoms() != 24:
        raise ValueError("NU6094 must contain 24 retained heavy atoms")
    q = Chem.MolFromPDBFile(str(destination / "1H1Q_prepared.pdb"), removeHs=False)
    s = Chem.MolFromPDBFile(str(destination / "1H1S_prepared.pdb"), removeHs=False)
    fixed, moving = backbone(q), backbone(s)
    xyz = parent.GetConformer().GetPositions()
    common = sorted(
        k for k in fixed.keys() & moving.keys() if np.linalg.norm(xyz - fixed[k], axis=1).min() <= 8
    )
    x, y = np.array([moving[k] for k in common]), np.array([fixed[k] for k in common])
    xc, yc = x.mean(0), y.mean(0)
    u, _, vt = np.linalg.svd((x - xc).T @ (y - yc))
    if np.linalg.det(u @ vt) < 0:
        u[:, -1] *= -1
    s_to_q = u @ vt
    translation = yc - xc @ s_to_q
    rotation = s_to_q.T
    q_to_s_translation = -translation @ rotation
    for index, position in enumerate(xyz @ rotation + q_to_s_translation):
        parent.GetConformer().SetAtomPosition(index, position)
    parent.SetProp("_Name", "NU6094; neutral9H; 1H1Q template protein-aligned to 1H1S")
    parent.SetProp("coordinate_frame", "Original 1H1S receptor coordinates; angstrom")
    parent.SetProp(
        "pose_origin",
        (
            "Experimental 1H1Q heavy atoms, rigidly protein-aligned; not an "
            "observed NU6094–1H1S complex"
        ),
    )
    with Chem.SDWriter(str(destination / "NU6094_template_1h1s.sdf")) as writer:
        writer.write(parent)
    alignment = {
        "source": "1H1Q",
        "destination": "1H1S",
        "rotation_row_vectors": rotation.tolist(),
        "translation_A": q_to_s_translation.tolist(),
        "matched_backbone_atoms": len(common),
        "backbone_rmsd_A": float(
            np.sqrt(np.mean(np.sum((x @ s_to_q + translation - y) ** 2, axis=1)))
        ),
        "selection": (
            "Common chain A N/CA/C/O within 8 A of observed NU6094 in 1H1Q; "
            "proper rigid fit; no ligand fitting"
        ),
        "matched_atom_ids": [list(k) for k in common],
    }
    (destination / "template_alignment.json").write_text(json.dumps(alignment, indent=2) + "\n")
    references = [
        {"name": "NU6094", "smiles": PARENT_SMILES, "source_pdb": "1H1Q"},
        {"name": "NU6102", "smiles": POSITIVE_SMILES, "source_pdb": "1H1S"},
    ]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "id": GROWTH_PREPARATION_ID,
        "protocol": "guided_growth_cdk2_v2",
        "name": "CDK2 · NU6094 para growth",
        "label": "CDK2 · NU6094 para growth",
        "recommended": True,
        "description": (
            "Grow one substituent from NU6094's para carbon toward Asp86 in an open CDK2 receptor."
        ),
        "receptor_pdb_id": "1H1S",
        "source": {
            "pdb": "1H1S",
            "url": "https://www.rcsb.org/structure/1H1S",
            "source_model": 1,
            "author_chains": ["A", "B"],
            "ligand": {"component": "4SP", "removed_from_receptor": True},
        },
        "parent": {
            "name": "NU6094",
            "source_pdb": "1H1Q",
            "source_url": "https://www.rcsb.org/structure/1H1Q",
            "component": "2A6",
            "pose_kind": "protein_aligned_template",
            "reference_label": "NU6094 template transferred from 1H1Q",
            "source_canonical_smiles": Chem.MolToSmiles(original),
            "prepared_smiles": desired,
            "preparation_transformations": [
                "Declared neutral9H state selected from the source CCD tautomer",
                "Heavy atoms transformed using protein backbone alignment only",
            ],
        },
        "coordinate_frame": {
            "id": GROWTH_PREPARATION_ID + ":original_1h1s",
            "units": "angstrom",
            "transform": "identity",
            "description": "Original 1H1S prepared receptor coordinates",
        },
        "preparation": {
            "receptor": (
                "Rigid 1H1S source chains A/B; TPO160 retained; waters removed; default altloc A"
            ),
            "ligand": (
                "Neutral9H NU6094 scaffold; 1H1Q coordinates transferred by protein alignment"
            ),
            "meeko_version": "0.8.0",
            "rdkit_version": "2025.9.6",
            "prolif_version": "2.2.3",
            "posebusters_version": "0.6.5",
            "no_pH_ensemble": True,
        },
        "scaffold": {
            "smiles": PARENT_SMILES,
            "libinvent_scaffold": "[*:0]c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1",
            "retained_heavy_atoms": 24,
            "ring_atoms": ["N1", "C2", "N3", "C4", "C5", "C6", "N7", "C8", "N9"],
            "attachment_atom_name": "C20",
            "attachment_label": "para carbon on the aniline ring",
        },
        "files": {
            "receptor_pdb": "1H1S_prepared.pdb",
            "receptor_pdbqt": "1H1S_prepared.pdbqt",
            "parent_sdf": "NU6094_template_1h1s.sdf",
            "template_source_pdb": "1H1Q_prepared.pdb",
            "template_source_sdf": "1H1Q_native.sdf",
            "template_alignment": "template_alignment.json",
        },
        "reference_candidates": references,
        "default_spec": {
            "schema_version": 1,
            "label": "CDK2 · NU6094 para growth",
            "target_preparation_id": GROWTH_PREPARATION_ID,
            "protocol": "guided_growth_cdk2_v2",
            "candidate_source": {
                "kind": "supplied",
                "candidates": [{"name": r["name"], "smiles": r["smiles"]} for r in references],
            },
            "limits": {
                "max_unique_candidates_evaluated": 12,
                "embedding_attempts_per_candidate": 16,
                "evaluation_admission_seconds": 600,
            },
            "seeds": {"embedding": 194715, "vina": 42},
            "constraints": {
                "max_molecular_weight": 450,
                "max_clogp": 4.5,
                "max_rotatable_bonds": 8,
                "formal_charge": 0,
            },
        },
        "validation_scope": {
            "kind": "retrospective_receptor_informed",
            "receptor_informed_by": (
                "The known NU6102 holo complex 1H1S was chosen as the open "
                "receptor; this is not fully prospective validation."
            ),
            "placement_inputs": (
                "Observed NU6094 heavy-atom template from 1H1Q and candidate molecular graph only."
            ),
            "target_ligand_coordinates_used_for_placement": False,
            "target_ligand_coordinates_used_for_selection": False,
            "reference_comparison": (
                "NU6102 coordinates are held out for retrospective RMSD/contact "
                "checks only; not included in this live preparation."
            ),
            "scope": (
                "Preserve NU6094 and add at most one substituent at C20; "
                "arbitrary molecules, other attachment sites and charge states "
                "are outside this workflow."
            ),
        },
        "limitations": [
            (
                "Receptor-informed retrospective workflow; no general "
                "cross-target or prospective docking accuracy claim."
            ),
            (
                "Rigid receptor, omitted waters and fixed neutral9H scaffold; no "
                "pH or protein ensemble."
            ),
            (
                "Only NU6094 para growth is supported; other sites and lost "
                "scaffolds are explicitly excluded."
            ),
            (
                "Computed contacts and Vina scores are hypotheses, not affinity, "
                "potency or synthesis validation."
            ),
            "The parent is a transferred template, not a native observed NU6094–1H1S complex.",
        ],
        "provenance": {
            "archive_license": "CC0-1.0",
            "source_urls": [
                "https://www.rcsb.org/structure/1H1Q",
                "https://www.rcsb.org/structure/1H1S",
                "https://doi.org/10.1038/nsb842",
            ],
            "prepared_source_sha256": {name: sha256(destination / name) for name in names},
            "template_alignment": alignment,
            "reproduction": (
                "python -m capychem.experiments.science_prepare --source-dir "
                "SOURCE --output-dir NEW_DIRECTORY"
            ),
        },
    }
    manifest["sha256"] = {
        path.name: sha256(path) for path in sorted(destination.iterdir()) if path.is_file()
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare(args.source_dir, args.output_dir)
    print(
        json.dumps(
            {"id": manifest["id"], "parent": manifest["parent"], "files": manifest["sha256"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
