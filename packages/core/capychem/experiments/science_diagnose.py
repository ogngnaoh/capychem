"""Controlled retrospective NU6102 placement diagnosis, never a production prediction.

Observed target coordinates are used only in clearly labelled control cases and
post-hoc RMSD measurements. Predicted starts use NU6102's graph and NU2058 only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import prolif as plf
from capychem.experiments.chemistry.conformers import generate
from capychem.experiments.chemistry.geometry import inspect_pose
from capychem.experiments.science import choose_pose
from capychem.experiments.science_config import load_preset, reference_data_dir, sha256
from meeko import MoleculePreparation, PDBQTMolecule, PDBQTWriterLegacy, RDKitMolCreate
from numpy.typing import NDArray
from posebusters import PoseBusters
from rdkit import Chem
from rdkit.Chem import rdMolAlign


def read_molecule(path: Path) -> Chem.Mol:
    mol = Chem.SDMolSupplier(str(path), removeHs=True)[0]
    if mol is None:
        raise ValueError(f"Could not read {path}")
    return mol


def write_molecule(mol: Chem.Mol, path: Path) -> None:
    with Chem.SDWriter(str(path)) as writer:
        writer.write(mol)


def transform(
    mol: Chem.Mol, rotation: NDArray[np.float64], translation: NDArray[np.float64]
) -> Chem.Mol:
    result = Chem.Mol(mol)
    for i, position in enumerate(mol.GetConformer().GetPositions() @ rotation + translation):
        result.GetConformer().SetAtomPosition(i, position)
    return result


def backbone(receptor: Chem.Mol) -> dict[tuple[str, int, str, str], NDArray[np.float64]]:
    result: dict[tuple[str, int, str, str], NDArray[np.float64]] = {}
    xyz = receptor.GetConformer().GetPositions()
    for atom in receptor.GetAtoms():
        info = atom.GetPDBResidueInfo()
        if info and info.GetChainId() == "A" and info.GetName().strip() in {"N", "CA", "C", "O"}:
            key = (
                info.GetChainId(),
                info.GetResidueNumber(),
                info.GetInsertionCode(),
                info.GetName().strip(),
            )
            result[key] = xyz[atom.GetIdx()]
    return result


def align_receptor(
    moving: Chem.Mol, fixed: Chem.Mol, parent: Chem.Mol
) -> tuple[NDArray[np.float64], NDArray[np.float64], dict[str, Any]]:
    moving_atoms, fixed_atoms = backbone(moving), backbone(fixed)
    ligand_xyz = parent.GetConformer().GetPositions()
    keys = sorted(
        k
        for k in moving_atoms.keys() & fixed_atoms.keys()
        if np.linalg.norm(ligand_xyz - fixed_atoms[k], axis=1).min() <= 8
    )
    x, y = np.array([moving_atoms[k] for k in keys]), np.array([fixed_atoms[k] for k in keys])
    xc, yc = x.mean(0), y.mean(0)
    u, _, vt = np.linalg.svd((x - xc).T @ (y - yc))
    if np.linalg.det(u @ vt) < 0:
        u[:, -1] *= -1
    rotation = u @ vt
    translation = yc - xc @ rotation
    return (
        rotation,
        translation,
        {
            "atoms": len(keys),
            "rmsd_A": float(
                np.sqrt(np.mean(np.sum((x @ rotation + translation - y) ** 2, axis=1)))
            ),
            "rotation": rotation.tolist(),
            "translation": translation.tolist(),
            "selection": "Chain A backbone N/CA/C/O within 8 A of parent; ligand not fitted",
        },
    )


def vina_case(
    molecule: Chem.Mol,
    receptor_pdbqt: Path,
    box: dict[str, list[float]],
    output: Path,
    name: str,
    binary: Path,
    mode: str,
    seed: int,
    exhaustiveness: int,
    scoring: str,
    flex: Path | None = None,
) -> tuple[list[tuple[Chem.Mol, float]], float]:
    start = time.perf_counter()
    setup = MoleculePreparation().prepare(Chem.AddHs(molecule, addCoords=True))[0]
    text, okay, error = PDBQTWriterLegacy.write_string(setup)
    if not okay:
        raise ValueError(error)
    input_path = output / f"{name}.input.pdbqt"
    output_path = output / f"{name}.output.pdbqt"
    input_path.write_text(text)
    command = [
        str(binary),
        "--receptor",
        str(receptor_pdbqt),
        "--ligand",
        str(input_path),
        "--cpu",
        "2" if mode == "dock" else "1",
        "--seed",
        str(seed),
        "--scoring",
        scoring,
    ]
    if flex:
        command.extend(["--flex", str(flex)])
    for axis, value in zip("xyz", box["center"], strict=True):
        command.extend([f"--center_{axis}", str(value)])
    for axis, value in zip("xyz", box["size"], strict=True):
        command.extend([f"--size_{axis}", str(value)])
    if mode == "dock":
        command.extend(
            [
                "--exhaustiveness",
                str(exhaustiveness),
                "--num_modes",
                "20",
                "--energy_range",
                "8",
                "--out",
                str(output_path),
            ]
        )
    elif mode == "local":
        command.extend(["--local_only", "--out", str(output_path)])
    else:
        command.append("--score_only")
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    (output / f"{name}.log").write_text(result.stdout + "\n" + result.stderr)
    (output / f"{name}.command.json").write_text(json.dumps(command, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:] or result.stdout[-1500:])
    if mode == "score":
        score_match = re.search(
            r"(?:Affinity|Estimated Free Energy of Binding)\s*:\s*([-+\d.]+)", result.stdout
        )
        if score_match is None:
            raise ValueError("Vina output did not contain an affinity score.")
        return [(Chem.Mol(molecule), float(score_match[1]))], time.perf_counter() - start
    reconstructed = RDKitMolCreate.from_pdbqt_mol(
        PDBQTMolecule.from_file(str(output_path), skip_typing=True)
    )[0]
    if mode == "dock":
        scores = [
            float(v)
            for v in re.findall(r"REMARK VINA RESULT:\s*([-+\d.]+)", output_path.read_text())
        ]
    else:
        score_match = re.search(
            r"(?:Affinity|Estimated Free Energy of Binding)\s*:\s*([-+\d.]+)", result.stdout
        )
        if score_match is None:
            raise ValueError("Vina output did not contain an affinity score.")
        scores = [float(score_match[1])]
    assert reconstructed.GetNumConformers() == len(scores)
    results = []
    for conf, score in zip(reconstructed.GetConformers(), scores, strict=True):
        pose = Chem.Mol(reconstructed)
        pose.RemoveAllConformers()
        pose.AddConformer(Chem.Conformer(conf), assignId=True)
        pose = Chem.AddHs(Chem.RemoveHs(pose), addCoords=True)
        assert Chem.MolToSmiles(Chem.RemoveHs(pose)) == Chem.MolToSmiles(Chem.RemoveHs(molecule))
        results.append((pose, score))
    return results, time.perf_counter() - start


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--vina", type=Path, required=True)
    parser.add_argument("--phases", default="controls,local,global")
    parser.add_argument("--attempts", type=int, default=32)
    parser.add_argument("--dock-seeds", default="42,43,44")
    parser.add_argument("--exhaustiveness", type=int, default=16)
    parser.add_argument("--scoring", default="vina", choices=["vina", "vinardo"])
    parser.add_argument("--receptors", default="parent,native")
    parser.add_argument("--flex-prefix", type=Path)
    args = parser.parse_args()
    if args.flex_prefix and (args.receptors != "parent" or "controls" in args.phases):
        parser.error("Flexible diagnostic supports graph-only parent receptor cases")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    data = reference_data_dir()
    preset = load_preset()
    parent = read_molecule(data / preset["files"]["parent_sdf"])
    observed_native = read_molecule(data / "1H1S_native.sdf")
    if not observed_native.HasSubstructMatch(parent):
        raise ValueError("NU6102 input tautomer does not match the fixed parent")
    parent_path = data / preset["files"]["receptor_pdb"]
    native_path = args.native_data_dir / "1H1S_prepared.pdb"
    parent_receptor = Chem.MolFromPDBFile(str(parent_path), removeHs=False)
    native_receptor = Chem.MolFromPDBFile(str(native_path), removeHs=False)
    rotation, translation, alignment = align_receptor(native_receptor, parent_receptor, parent)
    observed_aligned = transform(observed_native, rotation, translation)
    parent_in_native = transform(parent, rotation.T, -translation @ rotation.T)
    write_molecule(observed_aligned, output / "observed-protein-aligned-parent-frame.sdf")
    write_molecule(parent_in_native, output / "parent-template-native-frame.sdf")
    report: dict[str, Any] = {
        "purpose": "Retrospective diagnostic; observed-start cases are controls, not predictions",
        "args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "alignment": alignment,
        "inputs": {
            str(p): sha256(p)
            for p in [
                data / "1H1S_native.sdf",
                data / preset["files"]["parent_sdf"],
                parent_path,
                native_path,
                args.native_data_dir / "1H1S_prepared.pdbqt",
                data / preset["files"]["receptor_pdbqt"],
            ]
        },
        "cases": [],
        "selection_policy": "unchanged guided_local_cdk2_v1 eligibility and selection",
        "sources": [
            "https://www.rcsb.org/structure/1H1S",
            "https://autodock-vina.readthedocs.io/en/latest/docking_basic.html",
            "https://autodock-vina.readthedocs.io/en/latest/docking_python.html",
        ],
    }
    rings = [
        i
        for i, name in enumerate(json.loads(parent.GetProp("ccd_atom_names")))
        if name in preset["scaffold"]["ring_atoms"]
    ]
    buster = PoseBusters(config="dock")
    fingerprint = plf.Fingerprint(interactions=["HBDonor", "HBAcceptor"])
    contexts: dict[str, dict[str, Any]] = {
        "parent": {
            "parent": parent,
            "observed": observed_aligned,
            "receptor": parent_receptor,
            "pdb": parent_path,
            "pdbqt": data / preset["files"]["receptor_pdbqt"],
        },
        "native": {
            "parent": parent_in_native,
            "observed": observed_native,
            "receptor": native_receptor,
            "pdb": native_path,
            "pdbqt": args.native_data_dir / "1H1S_prepared.pdbqt",
        },
    }
    if args.flex_prefix:
        contexts["parent"]["pdbqt"] = Path(str(args.flex_prefix) + "_rigid.pdbqt")
        for suffix in ["_rigid.pdbqt", "_flex.pdbqt", ".json"]:
            path = Path(str(args.flex_prefix) + suffix)
            report["inputs"][str(path)] = sha256(path)
    for context in contexts.values():
        xyz = context["parent"].GetConformer().GetPositions()
        context["box"] = {
            "center": xyz.mean(0).tolist(),
            "size": (np.ptp(xyz, axis=0) + 18).tolist(),
        }

    def run_case(
        name: str,
        receptor_key: str,
        molecule: Chem.Mol,
        mode: str,
        seed: int = 42,
        diagnostic: bool = False,
    ) -> None:
        context = contexts[receptor_key]
        row: dict[str, Any] = {
            "id": name,
            "receptor": receptor_key,
            "mode": mode,
            "seed": seed,
            "uses_observed_target_coordinates": diagnostic,
            "poses": [],
        }
        start = time.perf_counter()
        try:
            write_molecule(molecule, output / f"{name}.start.sdf")
            poses, seconds = vina_case(
                molecule,
                context["pdbqt"],
                context["box"],
                output,
                name,
                args.vina,
                mode,
                seed,
                args.exhaustiveness,
                args.scoring,
                flex=Path(str(args.flex_prefix) + "_flex.pdbqt") if args.flex_prefix else None,
            )
            row["vina_seconds"] = seconds
            receptor_models = None
            if args.flex_prefix:
                export = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "meeko.cli.mk_export",
                        str(output / f"{name}.output.pdbqt"),
                        "-j",
                        str(args.flex_prefix) + ".json",
                        "-p",
                        str(output / f"{name}.receptors.pdb"),
                        "-s",
                        str(output / f"{name}.export.sdf"),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=120,
                )
                (output / f"{name}.export.log").write_text(export.stdout + "\n" + export.stderr)
                receptor_models = [
                    block
                    for block in (output / f"{name}.receptors.pdb").read_text().split("ENDMDL")
                    if block.strip()
                ]
                assert len(receptor_models) == len(poses)
            for index, (pose, score) in enumerate(poses):
                path = output / f"{name}.pose-{index:02d}.sdf"
                write_molecule(Chem.AddHs(pose, addCoords=True), path)
                saved = Chem.SDMolSupplier(str(path), removeHs=False)[0]
                pose_receptor, pose_receptor_path = context["receptor"], context["pdb"]
                if receptor_models is not None:
                    pose_receptor_path = output / f"{name}.receptor-{index:02d}.pdb"
                    pose_receptor_path.write_text(receptor_models[index] + "ENDMDL\n")
                    pose_receptor = Chem.MolFromPDBFile(str(pose_receptor_path), removeHs=False)
                    assert pose_receptor is not None
                evidence = inspect_pose(
                    saved,
                    context["parent"],
                    pose_receptor,
                    pose_receptor_path,
                    buster,
                    fingerprint,
                    rings,
                )
                rmsd = rdMolAlign.CalcRMS(
                    Chem.RemoveHs(saved), context["observed"], maxMatches=1000
                )
                row["poses"].append(
                    {
                        "id": f"{name}-pose-{index:02d}",
                        "score": score,
                        "rmsd_to_observed_A": rmsd,
                        "sdf": path.name,
                        "receptor_pdb": str(pose_receptor_path),
                        **evidence,
                    }
                )
            selected = choose_pose(row["poses"])
            row["selected_pose_id"] = selected["id"] if selected else None
            row["selected"] = (
                {
                    k: selected[k]
                    for k in [
                        "score",
                        "rmsd_to_observed_A",
                        "asp86_contact",
                        "review_ready",
                        "hinge_hbond_type_count",
                        "ring_drift_A",
                    ]
                }
                if selected
                else None
            )
            row["asp86_poses"] = sum(p["asp86_contact"] for p in row["poses"])
            row["eligible_asp86_poses"] = sum(
                p["asp86_contact"] and p["review_ready"] for p in row["poses"]
            )
        except Exception as error:
            row["error"] = f"{type(error).__name__}: {error}"
        row["seconds"] = time.perf_counter() - start
        report["cases"].append(row)
        (output / "diagnosis.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in row.items() if k != "poses"}), flush=True)

    phases = args.phases.split(",")
    receptors = args.receptors.split(",")
    if "controls" in phases:
        for receptor_key in receptors:
            observed = contexts[receptor_key]["observed"]
            run_case(
                f"observed-{receptor_key}-score", receptor_key, observed, "score", diagnostic=True
            )
            run_case(
                f"observed-{receptor_key}-local", receptor_key, observed, "local", diagnostic=True
            )
    if "local" in phases or "global" in phases:
        graph = Chem.MolFromSmiles(Chem.MolToSmiles(observed_native))
        assert not graph.GetNumConformers()
        mapping = graph.GetSubstructMatch(parent)
        conformers, attempts = generate(graph, parent, mapping, args.attempts, 194715)
        report["embedding_attempts"] = attempts
        report["generated_conformers"] = len(conformers)
        report["prediction_inputs"] = (
            "NU6102 graph only; parent NU2058 observed coordinates; no NU6102 "
            "coordinates used for generation, search or selection"
        )
        for index, item in enumerate(conformers):
            for receptor_key in receptors:
                pose = (
                    item["molecule"]
                    if receptor_key == "parent"
                    else transform(item["molecule"], rotation.T, -translation @ rotation.T)
                )
                if "local" in phases:
                    run_case(
                        f"embedded-{index:02d}-attempt-{item['attempt']:02d}-{receptor_key}-local",
                        receptor_key,
                        pose,
                        "local",
                    )
                if "global" in phases and index == 0:
                    for seed in map(int, args.dock_seeds.split(",")):
                        run_case(
                            f"global-seed-{seed}-{receptor_key}",
                            receptor_key,
                            pose,
                            "dock",
                            seed=seed,
                        )
        (output / "diagnosis.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
