"""Run one real, bounded structure-guided experiment outside the API process.

Usage: python -m capychem.experiments.science --input spec.json --output-dir run/
stdout contains newline-delimited progress events. report.json is a recoverable
snapshot; coordinates, manifests and logs are immutable artifacts of this attempt.
The curated CDK2 preset is the only supported target preparation in this version.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import json
import math
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from capychem.experiments.science_config import (
    MAX_RANDOM_SEED,
    MAX_SMILES_LENGTH,
    PROPERTY_CONSTRAINT_BOUNDS,
    PROTOCOL_TARGETS,
    canonical_json_sha256,
    engine_source_hashes,
    executable,
    load_preset,
    protocol_descriptor,
    reference_data_dir,
    sha256,
)

if TYPE_CHECKING:
    from rdkit import Chem


class ProgressEmitter(Protocol):
    def __call__(self, kind: str, **payload: Any) -> None: ...


LIMITATIONS = [
    "Predicted poses and geometric contacts are computational hypotheses, "
    "not measured affinity or potency.",
    "Only the curated rigid CDK2 1H1P preparation is supported; "
    "waters are omitted and the neutral 9H scaffold is fixed.",
    "LibInvent samples scaffold-compatible graphs "
    "without seeing the receptor or learning this objective.",
    "The full parent pose guides initial embedding only; "
    "ligand movement is released during Vina local refinement.",
    "The ring-drift and hinge criteria define review eligibility, not universally valid binding.",
    "Unspecified stereochemistry is resolved per generated conformer and recorded "
    "as separate prepared states; exhaustive isomer enumeration is not implemented.",
    "The known NU6102 contact was missed by the calibrated selected-pose protocol; "
    "no accuracy or improved-binding claim is made.",
]


def json_write(path: Path, value: object, *, atomic: bool = False) -> None:
    text = json.dumps(value, indent=2, allow_nan=False) + "\n"
    if atomic:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text)
        temporary.replace(path)
    else:
        with path.open("x") as handle:
            handle.write(text)


def normalize_spec(raw: dict[str, Any]) -> dict[str, Any]:
    protocol_id = raw.get("protocol", "guided_local_cdk2_v1")
    if protocol_id not in PROTOCOL_TARGETS:
        raise ValueError("Unsupported science protocol")
    target_id = raw.get("target_preparation_id", PROTOCOL_TARGETS[protocol_id])
    if target_id != PROTOCOL_TARGETS[protocol_id]:
        raise ValueError("Target preparation and science protocol do not match")
    growth = protocol_id == "guided_growth_cdk2_v2"
    source = dict(raw.get("candidate_source") or {})
    if source.get("kind") == "supplied":
        rows = source.get("candidates")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 256:
            raise ValueError("Supply between 1 and 256 candidate records")
        if any(
            not isinstance(row, dict)
            or not isinstance(row.get("smiles"), str)
            or len(row["smiles"]) > MAX_SMILES_LENGTH
            for row in rows
        ):
            raise ValueError(
                "Each supplied candidate needs a SMILES string of at most "
                f"{MAX_SMILES_LENGTH} characters"
            )
    elif source.get("kind") == "libinvent":
        source.setdefault("raw_proposal_count", 32)
        source.setdefault("seed", 43)
        if (
            isinstance(source["raw_proposal_count"], bool)
            or not isinstance(source["raw_proposal_count"], int)
            or not 2 <= source["raw_proposal_count"] <= 256
        ):
            raise ValueError("LibInvent proposal count must be 2–256")
    else:
        raise ValueError("candidate_source.kind must be supplied or libinvent")
    limits = {
        "max_unique_candidates_evaluated": 12 if growth else 24,
        "embedding_attempts_per_candidate": 16 if growth else 8,
        "evaluation_admission_seconds": 600,
        **raw.get("limits", {}),
    }
    for key, minimum, maximum in [
        ("max_unique_candidates_evaluated", 1, 256),
        ("embedding_attempts_per_candidate", 1, 32),
        ("evaluation_admission_seconds", 1, 3600),
    ]:
        if (
            isinstance(limits[key], bool)
            or not isinstance(limits[key], (int, float))
            or not minimum <= limits[key] <= maximum
        ):
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
        if key != "evaluation_admission_seconds" and int(limits[key]) != limits[key]:
            raise ValueError(f"{key} must be an integer")
    seeds = {"embedding": 194715, "vina": 42, **raw.get("seeds", {})}
    for value in [*seeds.values(), source.get("seed", 43)]:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= MAX_RANDOM_SEED
        ):
            raise ValueError(f"Seeds must be integers between 0 and {MAX_RANDOM_SEED}")
    constraints = {
        "max_molecular_weight": 450,
        "max_clogp": 4.5,
        "max_rotatable_bonds": 8,
        "formal_charge": 0,
        **raw.get("constraints", {}),
    }
    if (
        isinstance(constraints["formal_charge"], bool)
        or not isinstance(constraints["formal_charge"], int)
        or constraints["formal_charge"] != 0
    ):
        raise ValueError("This protocol supports the neutral-charge profile only")
    for key, (minimum, maximum) in PROPERTY_CONSTRAINT_BOUNDS.items():
        value = constraints[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not minimum <= value <= maximum
        ):
            raise ValueError(f"{key} must be a finite number between {minimum} and {maximum}")
    if int(constraints["max_rotatable_bonds"]) != constraints["max_rotatable_bonds"]:
        raise ValueError("max_rotatable_bonds must be an integer")
    return {
        "schema_version": 1,
        "target_preparation_id": target_id,
        "protocol": protocol_id,
        "candidate_source": source,
        "limits": limits,
        "seeds": seeds,
        "constraints": constraints,
        "label": str(raw.get("label", "CDK2 design round"))[:200],
    }


def choose_pose(poses: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [pose for pose in poses if pose["review_ready"]]
    target = [pose for pose in eligible if pose["asp86_contact"]]
    pool = target or eligible or poses
    return min(pool, key=lambda pose: (pose["score"], pose["id"])) if pool else None


def error_kind(exc: Exception) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "timeout"
    if "outside the grid box" in str(exc):
        return "outside_grid"
    return "evaluation_failed"


def run(
    spec: dict[str, Any],
    output: Path,
    emit: ProgressEmitter,
    request_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Heavy imports live exclusively inside this isolated process.
    import numpy as np
    import prolif as plf
    from capychem.experiments.chemistry.conformers import generate
    from capychem.experiments.chemistry.geometry import (
        depiction,
        inspect_pose,
        properties,
        state_identity,
        viewer_structure,
        write_sdf,
    )
    from capychem.experiments.chemistry.identity import scaffold_query
    from meeko import MoleculePreparation, PDBQTMolecule, PDBQTWriterLegacy, RDKitMolCreate
    from posebusters import PoseBusters
    from rdkit import Chem, RDLogger
    from rdkit.Chem.MolStandardize import rdMolStandardize

    RDLogger.DisableLog("rdApp.warning")
    started = time.perf_counter()
    request_spec = spec if request_spec is None else request_spec
    descriptor = protocol_descriptor(spec["protocol"])
    expected_fingerprint = request_spec.get("resolved_protocol", {}).get("engine_fingerprint")
    if expected_fingerprint and expected_fingerprint != descriptor["engine_fingerprint"]:
        raise ValueError("Science implementation changed after submission; create a new experiment")
    preset = load_preset(spec["target_preparation_id"])
    source_dir = reference_data_dir(spec["target_preparation_id"])
    parent_name = preset.get("parent", {}).get("name", "NU2058")
    receptor_pdb_id = preset["source"]["pdb"]
    coordinate_frame = f"Original {receptor_pdb_id} receptor coordinates; angstrom"
    vina = executable("CAPYCHEM_VINA_BINARY", "vina")
    if not vina:
        raise ValueError("AutoDock Vina is missing; configure CAPYCHEM_VINA_BINARY")
    version = subprocess.run([vina, "--version"], capture_output=True, text=True, timeout=10)
    version_text = (version.stdout + version.stderr).strip()
    if version.returncode or "1.2.7" not in version_text:
        raise ValueError(f"This protocol requires Vina 1.2.7, got: {version_text[:200]}")
    for name in ["inputs", "poses", "views", "depictions", "logs"]:
        (output / name).mkdir(exist_ok=False)
    for name in preset["files"].values():
        shutil.copyfile(source_dir / name, output / "inputs" / name)
    json_write(output / "inputs/preset.json", preset)
    json_write(output / "inputs/spec.json", spec)
    json_write(output / "inputs/request.json", request_spec)
    parent = Chem.SDMolSupplier(
        str(output / "inputs" / preset["files"]["parent_sdf"]), removeHs=True
    )[0]
    if parent is None:
        raise ValueError("Parent SDF could not be read")
    parent_names = json.loads(parent.GetProp("ccd_atom_names"))
    parent_query = scaffold_query(parent)
    ring = [i for i, name in enumerate(parent_names) if name in preset["scaffold"]["ring_atoms"]]
    attachment_name = preset["scaffold"]["attachment_atom_name"]
    attachment_index = parent_names.index(attachment_name)
    retained_atoms = preset["scaffold"]["retained_heavy_atoms"]
    if len(ring) != 9 or parent.GetNumAtoms() != retained_atoms:
        raise ValueError("Preset scaffold atom identity check failed")
    receptor_path = output / "inputs" / preset["files"]["receptor_pdb"]
    receptor = Chem.MolFromPDBFile(str(receptor_path), removeHs=False)
    if receptor is None:
        raise ValueError("Prepared receptor PDB could not be read")
    receptor_pdbqt = output / "inputs" / preset["files"]["receptor_pdbqt"]
    pxyz = parent.GetConformer().GetPositions()
    box = {"center": pxyz.mean(0).tolist(), "size": (np.ptp(pxyz, axis=0) + 18).tolist()}
    protocol: dict[str, Any] = {
        "id": spec["protocol"],
        "version": descriptor["revision"],
        "preparation": preset["preparation"],
        "scaffold": preset["scaffold"],
        "initial_prior": f"all {retained_atoms} parent/template heavy atoms; "
        "RDKit constrained embedding with UFF tethers",
        "placement_reference": preset.get(
            "parent", {"name": "NU2058", "source_pdb": "1H1P", "pose_kind": "observed"}
        ),
        "validation_scope": preset.get("validation_scope", {"kind": "legacy_retrospective"}),
        "conformer_adapter": "FEgrow mapped embedding procedure, isolated adaptation, v1",
        "refinement": "Vina local_only; ligand translation/orientation/torsions released; "
        "rigid receptor",
        "vina": {
            "version": version_text,
            "seed": spec["seeds"]["vina"],
            "cpu_threads": 1,
            "timeout_seconds": 120,
        },
        "box": box,
        "embedding": {
            "attempts": spec["limits"]["embedding_attempts_per_candidate"],
            "seed_start": spec["seeds"]["embedding"],
            "duplicate_rms_A": 0.5,
        },
        "posebusters_config": "dock",
        "contact_types": ["HBDonor", "HBAcceptor"],
        "review": {
            "geometry_required": True,
            "ring_drift_max_A": 2.0,
            "hinge_residues": ["GLU81.A", "LEU83.A"],
            "minimum_hinge_interaction_types": 1,
        },
        "objective": "Seek an ASP86.A hydrogen-bond hypothesis while retaining a hinge-local pose",
        "selection": "Prefer review-ready Asp86-contact poses, then lowest Vina score; "
        "otherwise eligible minimum; otherwise flagged minimum",
        "parent_baseline": "Independent local refinement of observed parent pose; "
        "no previously computed control score is reused",
        "admission_budget": "Elapsed evaluation time checked before each candidate; "
        "not a hard run deadline",
    }
    json_write(output / "inputs/protocol.json", protocol)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "live_computation",
        "status": "running",
        "spec": spec,
        "protocol_manifest": protocol,
        "provenance": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "versions": {
                name: importlib.metadata.version(name)
                for name in ["rdkit", "numpy", "meeko", "posebusters", "prolif"]
            },
            "vina_binary_sha256": sha256(Path(vina)),
            "preset_sha256": sha256(source_dir / "manifest.json"),
            "spec_sha256": sha256(output / "inputs/spec.json"),
            "protocol_sha256": sha256(output / "inputs/protocol.json"),
            "engine_source_sha256": engine_source_hashes(),
            "engine_fingerprint": descriptor["engine_fingerprint"],
            "request_spec_sha256": canonical_json_sha256(request_spec),
        },
        "target": {
            "id": preset["id"],
            "receptor_pdb": f"inputs/{preset['files']['receptor_pdb']}",
            "receptor_pdbqt": f"inputs/{preset['files']['receptor_pdbqt']}",
            "frame": preset["coordinate_frame"],
        },
        "parent": {
            "name": parent_name,
            "pose_kind": preset.get("parent", {}).get("pose_kind", "observed"),
            "reference_label": preset.get("parent", {}).get(
                "reference_label", "Observed NU2058 in 1H1P"
            ),
            "smiles": Chem.MolToSmiles(parent),
            "observed_sdf": "poses/parent-observed.sdf",
            "view_json": "views/parent-observed.json",
        },
        "records": [],
        "request_spec": request_spec,
        "protocol_descriptor": descriptor,
        "summary": {},
        "limitations": (LIMITATIONS if descriptor["revision"] == 1 else [LIMITATIONS[0]])
        + preset.get("limitations", []),
    }
    buster = PoseBusters(config="dock")
    fingerprint = plf.Fingerprint(interactions=["HBDonor", "HBAcceptor"])

    def snapshot() -> None:
        report["seconds"] = time.perf_counter() - started
        records = report["records"]
        statuses = sorted({record["status"] for record in records})
        report["summary"] = {
            status: sum(record["status"] == status for record in records) for status in statuses
        }
        report["summary"].update(
            {
                "raw_proposals": len(report.get("raw_proposals", records)),
                "processed_proposals": len(records),
                "unique_candidates": sum(
                    record["status"] not in {"invalid", "duplicate"} for record in records
                ),
                "evaluated_candidates": sum(record.get("evaluated", False) for record in records),
                "pose_count": sum(len(record.get("poses", [])) for record in records),
                "pose_failures": sum(len(record.get("pose_errors", [])) for record in records),
                "objective_hits": sum(
                    any(p["review_ready"] and p["asp86_contact"] for p in record.get("poses", []))
                    for record in records
                ),
            }
        )
        json_write(output / "report.json", report, atomic=True)

    def evaluate(initial: Chem.Mol, pose_id: str, name: str) -> dict[str, Any]:
        pose_started = time.perf_counter()
        paths = {
            "input": f"poses/{pose_id}-input.pdbqt",
            "output": f"poses/{pose_id}-output.pdbqt",
            "log": f"logs/{pose_id}.log",
            "sdf": f"poses/{pose_id}.sdf",
            "view": f"views/{pose_id}.json",
        }
        setup = MoleculePreparation().prepare(Chem.AddHs(initial, addCoords=True))[0]
        pdbqt, okay, error = PDBQTWriterLegacy.write_string(setup)
        if not okay:
            raise ValueError(error)
        (output / paths["input"]).write_text(pdbqt)
        command = [
            vina,
            "--receptor",
            str(receptor_pdbqt),
            "--ligand",
            str(output / paths["input"]),
            "--cpu",
            "1",
            "--seed",
            str(spec["seeds"]["vina"]),
            "--local_only",
            "--out",
            str(output / paths["output"]),
        ]
        for axis, value in zip("xyz", box["center"], strict=True):
            command.extend([f"--center_{axis}", f"{value:.5f}"])
        for axis, value in zip("xyz", box["size"], strict=True):
            command.extend([f"--size_{axis}", f"{value:.5f}"])
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired as exc:
            (output / paths["log"]).write_text("Vina exceeded the 120 second per-pose timeout.\n")
            raise exc
        (output / paths["log"]).write_text(result.stdout + "\n" + result.stderr)
        if result.returncode:
            raise RuntimeError(result.stderr[-1500:] or result.stdout[-1500:])
        match = re.search(
            r"(?:Affinity|Estimated Free Energy of Binding)\s*:\s*([-+\d.]+)", result.stdout
        )
        if not match:
            raise ValueError("Vina did not return a parseable score")
        reconstructed = RDKitMolCreate.from_pdbqt_mol(
            PDBQTMolecule.from_file(str(output / paths["output"]), skip_typing=True)
        )[0]
        if reconstructed is None or reconstructed.GetNumConformers() != 1:
            raise ValueError("Vina output is not one interpretable molecular pose")
        mol = Chem.AddHs(Chem.RemoveHs(reconstructed), addCoords=True)
        expected = Chem.MolToSmiles(Chem.RemoveHs(initial), isomericSmiles=True)
        actual = Chem.MolToSmiles(Chem.RemoveHs(mol), isomericSmiles=True)
        if actual != expected:
            raise ValueError("Vina reconstruction changed graph or resolved stereochemistry")
        write_sdf(mol, output / paths["sdf"], f"{name}; {pose_id}; predicted", coordinate_frame)
        # Assess the saved artifact so the viewer and evidence share its precision.
        mol = Chem.SDMolSupplier(str(output / paths["sdf"]), removeHs=False)[0]
        evidence = inspect_pose(mol, parent, receptor, receptor_path, buster, fingerprint, ring)
        state_id, prepared_smiles = state_identity(mol)
        view = viewer_structure(
            mol, parent, receptor, preset, pose_id, name, evidence, paths["sdf"]
        )
        json_write(output / paths["view"], view)
        pose = {
            "id": pose_id,
            "prepared_state_id": state_id,
            "prepared_smiles": prepared_smiles,
            "sdf": paths["sdf"],
            "view_json": paths["view"],
            "log": paths["log"],
            "score": float(match[1]),
            "score_unit": "Vina kcal/mol model score",
            "seconds": time.perf_counter() - pose_started,
            "atom_mapping": view["atomMapping"],
            **evidence,
        }
        return pose

    emit(
        "stage.started",
        stage="prepare",
        message="Verifying the curated receptor and parent coordinates",
    )
    observed = Chem.AddHs(parent, addCoords=True)
    write_sdf(
        observed,
        output / "poses/parent-observed.sdf",
        f"{parent_name}; reference template heavy atoms with prepared hydrogens",
        coordinate_frame,
    )
    observed = Chem.SDMolSupplier(str(output / "poses/parent-observed.sdf"), removeHs=False)[0]
    observed_evidence = inspect_pose(
        observed, parent, receptor, receptor_path, buster, fingerprint, ring
    )
    json_write(
        output / "views/parent-observed.json",
        viewer_structure(
            observed,
            parent,
            receptor,
            preset,
            "parent-observed",
            parent_name,
            observed_evidence,
            "poses/parent-observed.sdf",
            origin="template"
            if preset.get("parent", {}).get("pose_kind") == "protein_aligned_template"
            else "observed",
        ),
    )
    report["parent"]["observed_evidence"] = observed_evidence
    depiction(parent, output / "depictions/parent.svg")
    report["parent"]["depiction_svg"] = "depictions/parent.svg"
    snapshot()
    emit("stage.completed", stage="prepare")
    emit(
        "stage.started",
        stage="baseline",
        message="Computing the parent baseline with the same receptor and scoring setup",
    )
    report["parent"]["baseline_pose"] = evaluate(
        observed, "parent-baseline", f"{parent_name} baseline"
    )
    snapshot()
    emit("stage.completed", stage="baseline", score=report["parent"]["baseline_pose"]["score"])

    emit("stage.started", stage="generate")
    source = spec["candidate_source"]
    if source["kind"] == "libinvent":
        request = {
            "raw_proposal_count": int(source["raw_proposal_count"]),
            "seed": source["seed"],
            "scaffold": preset["scaffold"]["libinvent_scaffold"],
        }
        json_write(output / "inputs/generation.json", request)
        generator_python = executable("CAPYCHEM_GENERATOR_PYTHON", sys.executable)
        if not generator_python:
            raise ValueError("Configure CAPYCHEM_GENERATOR_PYTHON")
        generator_result = subprocess.run(
            [
                generator_python,
                "-m",
                "capychem.experiments.chemistry.generate",
                "--input",
                str(output / "inputs/generation.json"),
                "--output",
                str(output / "generation.json"),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        (output / "logs/generation.log").write_text(
            generator_result.stdout + "\n" + generator_result.stderr
        )
        if generator_result.returncode:
            raise RuntimeError("LibInvent generation failed: " + generator_result.stderr[-2000:])
        generation = json.loads((output / "generation.json").read_text())
        proposals = generation.pop("records")
        report["generation"] = generation
    else:
        proposals = source["candidates"]
        report["generation"] = {"source": "supplied", "count": len(proposals), "seconds": 0}
    report["source_accounting"] = {
        "requested": int(source.get("raw_proposal_count", len(proposals))),
        "returned": len(proposals),
    }
    report["raw_proposals"] = proposals
    snapshot()
    emit("stage.completed", stage="generate", count=len(proposals))

    evaluated = 0
    evaluation_started = time.perf_counter()
    seen: dict[str, str] = {}
    emit("stage.started", stage="evaluate", total=len(proposals))
    for index, proposal in enumerate(proposals):
        candidate_started = time.perf_counter()
        candidate_id = f"candidate-{index:04d}"
        raw_smiles = proposal.get("smiles")
        record: dict[str, Any] = {
            "id": candidate_id,
            "name": str(proposal.get("name") or f"Candidate {index + 1}")[:200],
            "proposal_index": index,
            "source": source["kind"],
            "proposal_smiles": raw_smiles,
            "canonical_smiles": None,
            "status": "invalid",
            "properties": None,
            "filter_failures": [],
            "prepared_states": [],
            "poses": [],
            "pose_errors": [],
            "embedding_attempts": [],
            "selected_pose_id": None,
            "partial": False,
            "evaluated": False,
        }
        if source["kind"] == "libinvent":
            record["generation_metadata"] = {
                key: proposal.get(key) for key in ["decoration", "model_nll", "valid"]
            }
        report["records"].append(record)
        try:
            if not raw_smiles:
                raise ValueError("Generator returned an invalid molecular graph")
            mol = Chem.MolFromSmiles(raw_smiles)
            if mol is None:
                raise ValueError("SMILES could not be parsed")
            if len(Chem.GetMolFrags(mol)) != 1 or any(
                a.GetAtomicNum() == 0 for a in mol.GetAtoms()
            ):
                raise ValueError("Only one connected molecule without dummy atoms is supported")
            original_canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
            if not mol.HasSubstructMatch(parent_query, useChirality=True):
                states = [
                    state
                    for state in rdMolStandardize.TautomerEnumerator().Enumerate(mol)
                    if state.HasSubstructMatch(parent_query, useChirality=True)
                ]
                if len(states) == 1:
                    mol = states[0]
                    record["preparation_transformations"] = [
                        "Selected the unique tautomer containing "
                        "the declared neutral 9H parent scaffold"
                    ]
            canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
            record["canonical_smiles"] = original_canonical
            record["normalized_smiles"] = canonical
            record["properties"] = properties(mol)
            record["unspecified_stereo"] = [
                {"type": str(item.type), "index": int(item.centeredOn)}
                for item in Chem.FindPotentialStereo(mol)
                if str(item.specified) == "Unspecified"
            ]
            if canonical in seen:
                record.update(status="duplicate", duplicate_of=seen[canonical])
                continue
            seen[canonical] = candidate_id
            record["depiction_svg"] = f"depictions/{candidate_id}.svg"
            depiction(mol, output / record["depiction_svg"])
            match = mol.GetSubstructMatch(parent_query, useChirality=True)
            failures = record["filter_failures"]
            if len(match) != retained_atoms:
                failures.append("parent_scaffold_not_retained")
            else:
                scaffold_set = set(match)
                cross_bonds = [
                    b
                    for b in mol.GetBonds()
                    if (b.GetBeginAtomIdx() in scaffold_set) != (b.GetEndAtomIdx() in scaffold_set)
                ]
                if (
                    any(
                        match[attachment_index] not in [b.GetBeginAtomIdx(), b.GetEndAtomIdx()]
                        for b in cross_bonds
                    )
                    or len(cross_bonds) > 1
                ):
                    failures.append(
                        "modification_outside_single_N2_attachment"
                        if attachment_name == "N2"
                        else "modification_outside_declared_para_attachment"
                    )
                record["parent_to_candidate_atom_map"] = list(match)
            constraints = spec["constraints"]
            for prop, bound in [
                ("molecular_weight", "max_molecular_weight"),
                ("clogp", "max_clogp"),
                ("rotatable_bonds", "max_rotatable_bonds"),
            ]:
                if record["properties"][prop] > constraints[bound]:
                    failures.append(f"{prop}>{constraints[bound]}")
            if record["properties"]["formal_charge"] != constraints["formal_charge"]:
                failures.append("formal_charge!=0")
            if failures:
                record["status"] = "outside_constraints"
                continue
            if (
                evaluated >= spec["limits"]["max_unique_candidates_evaluated"]
                or time.perf_counter() - evaluation_started
                >= spec["limits"]["evaluation_admission_seconds"]
            ):
                record.update(
                    status="deferred_budget",
                    deferred_reason="candidate_or_evaluation_admission_budget",
                )
                continue
            evaluated += 1
            record["evaluated"] = True
            record["status"] = "evaluating"
            conformers, attempts = generate(
                mol,
                parent,
                match,
                int(spec["limits"]["embedding_attempts_per_candidate"]),
                spec["seeds"]["embedding"],
            )
            record["embedding_attempts"] = attempts
            record["generated_conformer_count"] = len(conformers)
            states_by_id: dict[str, dict[str, Any]] = {}
            for conformer_index, conformer in enumerate(conformers):
                pose_id = f"{candidate_id}-pose-{conformer_index:03d}"
                try:
                    pose = evaluate(conformer["molecule"], pose_id, record["name"])
                    pose["embedding_seed"] = conformer["seed"]
                    pose["embedding_attempt"] = conformer["attempt"]
                    pose["delta_score_vs_parent"] = (
                        pose["score"] - report["parent"]["baseline_pose"]["score"]
                    )
                    record["poses"].append(pose)
                    states_by_id[pose["prepared_state_id"]] = {
                        "id": pose["prepared_state_id"],
                        "smiles": pose["prepared_smiles"],
                        "stereochemistry_policy": "Coordinate-derived state; "
                        "explicitly specified stereo preserved",
                        "proposal_had_unspecified_stereo": bool(record["unspecified_stereo"]),
                    }
                except Exception as exc:
                    record["pose_errors"].append(
                        {
                            "id": pose_id,
                            "kind": error_kind(exc),
                            "message": str(exc)[-2000:],
                            "embedding_seed": conformer["seed"],
                            "log": f"logs/{pose_id}.log"
                            if (output / f"logs/{pose_id}.log").exists()
                            else None,
                        }
                    )
            record["prepared_states"] = list(states_by_id.values())
            selected = choose_pose(record["poses"])
            record["selected_pose_id"] = selected["id"] if selected else None
            record["status"] = (
                ("ready_for_review" if selected["review_ready"] else "needs_review")
                if selected
                else "no_pose"
            )
            record["partial"] = bool(
                record["pose_errors"] or any(a["status"] == "failed" for a in attempts)
            )
        except Exception as exc:
            record["error"] = str(exc)[-2000:]
            record["status"] = "evaluation_error" if record["evaluated"] else "invalid"
        finally:
            record["seconds"] = time.perf_counter() - candidate_started
            snapshot()
            emit(
                "candidate.complete",
                stage="evaluate",
                candidate_id=candidate_id,
                status=record["status"],
                completed=index + 1,
                total=len(proposals),
                pose_count=len(record["poses"]),
            )
    report["status"] = "complete"
    report["evaluation_seconds"] = time.perf_counter() - evaluation_started
    snapshot()
    report["execution_outcome"] = (
        "completed_with_errors"
        if any(
            r["partial"] or r["status"] in {"evaluation_error", "no_pose"}
            for r in report["records"]
        )
        else "completed"
    )
    report["scientific_outcome"] = (
        "review_candidates"
        if report["summary"].get("ready_for_review", 0)
        else "no_eligible_candidates"
    )
    report["objective_outcome"] = (
        "detected_contact_candidates"
        if report["summary"]["objective_hits"]
        else "no_detected_contact_candidates"
        if report["summary"]["pose_count"]
        else "not_assessed"
    )
    report["artifacts"] = [
        {
            "path": str(path.relative_to(output)),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(output.rglob("*"))
        if path.is_file()
        and not (
            path.parent == output
            and path.name
            in {"report.json", "report.json.tmp", "input.json", "progress.jsonl", "stderr.log"}
        )
    ]
    snapshot()
    emit(
        "experiment.complete",
        stage="complete",
        summary=report["summary"],
        scientific_outcome=report["scientific_outcome"],
        objective_outcome=report["objective_outcome"],
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "report.json").exists():
        parser.error("Output contains an existing report; use a new attempt directory")
    sequence = 0
    real_stdout = sys.stdout

    def emit(kind: str, **payload: Any) -> None:
        nonlocal sequence
        sequence += 1
        real_stdout.write(
            json.dumps({"type": kind, "sequence": sequence, **payload}, allow_nan=False) + "\n"
        )
        real_stdout.flush()

    try:
        request_spec = json.loads(args.input.read_text())
        spec = normalize_spec(request_spec)
        with contextlib.redirect_stdout(sys.stderr):
            run(spec, output, emit, request_spec=request_spec)
        return 0
    except Exception as exc:
        report_path = output / "report.json"
        report = (
            json.loads(report_path.read_text())
            if report_path.exists()
            else {"schema_version": 1, "kind": "live_computation", "records": []}
        )
        report.update(
            status="failed", error={"kind": type(exc).__name__, "message": str(exc)[-3000:]}
        )
        json_write(report_path, report, atomic=True)
        emit("experiment.failed", error=report["error"])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
