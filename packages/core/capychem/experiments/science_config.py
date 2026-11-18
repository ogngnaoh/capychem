"""Lightweight configuration for the isolated molecular calculation process.

This module deliberately imports no chemistry or model packages so the API can
read the preset and report setup requirements from its own Python environment.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

LIBINVENT_SHA256 = "03e6cbe8a53e59a4ac3aa6728d041f1957bdd07b5eefdf2cfc5c8591036075af"
REINVENT_COMMIT = "0f075b349ed22015e0406350c6f426701bb0815d"
VINA_VERSION = "1.2.7"
LEGACY_PREPARATION_ID = "cdk2_1h1p"
GROWTH_PREPARATION_ID = "cdk2_1h1s_nu6094_v1"
PROTOCOL_TARGETS = {
    "guided_local_cdk2_v1": LEGACY_PREPARATION_ID,
    "guided_growth_cdk2_v2": GROWTH_PREPARATION_ID,
}
# Leave room for deterministic per-attempt offsets within RDKit's signed seed range.
MAX_RANDOM_SEED = 2147483000
MAX_SMILES_LENGTH = 4096
PROPERTY_CONSTRAINT_BOUNDS = {
    "max_molecular_weight": (100, 1000),
    "max_clogp": (-5, 10),
    "max_rotatable_bonds": (0, 30),
}


def reference_data_dir(target_preparation_id: str = LEGACY_PREPARATION_ID) -> Path:
    configured = os.environ.get("CAPYCHEM_CDK2_DATA_DIR")
    base = (
        Path(configured).expanduser().resolve()
        if configured
        else Path(__file__).resolve().parents[4] / "data/reference/cdk2"
    )
    if target_preparation_id == LEGACY_PREPARATION_ID:
        return base
    if target_preparation_id == GROWTH_PREPARATION_ID:
        return base / "preparations" / target_preparation_id
    raise ValueError(f"Unsupported target preparation: {target_preparation_id}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def engine_source_hashes() -> dict[str, str]:
    directory = Path(__file__).parent
    return {
        str(path.relative_to(directory)): sha256(path)
        for path in [
            directory / "science.py",
            directory / "science_config.py",
            *sorted(directory.joinpath("chemistry").glob("*.py")),
        ]
    }


def engine_fingerprint() -> str:
    return canonical_json_sha256(engine_source_hashes())


def protocol_descriptor(protocol_id: str) -> dict[str, Any]:
    if protocol_id not in PROTOCOL_TARGETS:
        raise ValueError(f"Unsupported science protocol: {protocol_id}")
    hashes = engine_source_hashes()
    descriptor: dict[str, Any] = {
        "id": protocol_id,
        "revision": 1 if protocol_id == "guided_local_cdk2_v1" else 2,
        "target_preparation_id": PROTOCOL_TARGETS[protocol_id],
        "placement": "full_parent_initial_prior_then_free_ligand_local_refinement",
        "ring_locality_max_A": 2.0,
        "minimum_hinge_contact_types": 1,
        "objective": "Explore an Asp86 polar contact while retaining a plausible hinge-local pose",
        "selection": "review_ready_then_Asp86_if_present_then_lowest_Vina",
        "protein_motion": "rigid",
        "cloud_compute": False,
        "engine_fingerprint": canonical_json_sha256(hashes),
        "implementation_sha256": hashes,
    }
    if protocol_id == "guided_growth_cdk2_v2":
        descriptor.update(
            placement="NU6094_24_atom_protein_aligned_template_then_free_ligand_local_refinement",
            parent_name="NU6094",
            attachment="para carbon C20",
            retained_heavy_atoms=24,
            validation_scope="Retrospective receptor-informed: 1H1S is the NU6102 holo receptor; "
            "NU6102 ligand coordinates are excluded from placement and selection",
        )
    return descriptor


def load_preset(
    target_preparation_id: str = LEGACY_PREPARATION_ID, *, verify: bool = True
) -> dict[str, Any]:
    directory = reference_data_dir(target_preparation_id)
    preset: dict[str, Any] = json.loads((directory / "manifest.json").read_text())
    if preset["id"] != target_preparation_id:
        raise ValueError("Target preparation directory and manifest identity disagree")
    if verify:
        for name, expected in preset["sha256"].items():
            path = directory / name
            if path.parent != directory or not path.is_file() or sha256(path) != expected:
                raise ValueError(f"Reference artifact failed integrity check: {name}")
    return preset


def supported_presets(*, verify: bool = True) -> list[dict[str, Any]]:
    return [
        load_preset(GROWTH_PREPARATION_ID, verify=verify),
        load_preset(LEGACY_PREPARATION_ID, verify=verify),
    ]


def executable(name: str, fallback: str) -> str | None:
    configured = os.environ.get(name)
    if configured:
        path = Path(configured).expanduser()
        # Resolving a venv's python symlink loses its pyvenv.cfg environment.
        return str(path.absolute()) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(fallback)


def readiness() -> dict[str, Any]:
    """Configuration presence only; dependency imports are checked by the worker."""
    problems: list[str] = []
    try:
        supported_presets(verify=True)
    except (OSError, ValueError, KeyError) as exc:
        problems.append(str(exc))
    python = executable("CAPYCHEM_SCIENCE_PYTHON", "python3")
    vina = executable("CAPYCHEM_VINA_BINARY", "vina")
    if not python:
        problems.append("Configure CAPYCHEM_SCIENCE_PYTHON with the science environment Python.")
    if not vina:
        problems.append("Configure CAPYCHEM_VINA_BINARY with AutoDock Vina 1.2.7.")
    generator_python = executable("CAPYCHEM_GENERATOR_PYTHON", sys.executable)
    checkpoint = Path(os.environ.get("CAPYCHEM_LIBINVENT_CHECKPOINT", "/missing"))
    source = Path(os.environ.get("CAPYCHEM_REINVENT_SOURCE", "/missing"))
    generator_ready = bool(
        generator_python and checkpoint.is_file() and (source / "reinvent").is_dir()
    )
    return {
        "configured": not problems,
        "dependency_imports_verified": False,
        "problems": problems,
        "science_python": python,
        "vina_binary": vina,
        "libinvent_configured": generator_ready,
        "reference_data_dir": str(reference_data_dir()),
    }
