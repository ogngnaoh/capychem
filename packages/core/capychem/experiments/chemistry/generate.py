"""Isolated LibInvent CPU sampling adapter, invoked in its model environment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from capychem.experiments.science_config import LIBINVENT_SHA256, REINVENT_COMMIT


def run(request: dict[str, Any]) -> dict[str, Any]:
    source = Path(os.environ.get("CAPYCHEM_REINVENT_SOURCE", ""))
    checkpoint = Path(os.environ.get("CAPYCHEM_LIBINVENT_CHECKPOINT", ""))
    if not (source / "reinvent").is_dir() or not checkpoint.is_file():
        raise ValueError(
            "LibInvent is not configured; run scripts/setup_science.py --with-generator"
        )
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if digest != LIBINVENT_SHA256:
        raise ValueError("LibInvent checkpoint failed the verified official SHA256 check")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if commit != REINVENT_COMMIT:
        raise ValueError(f"REINVENT source must be pinned to {REINVENT_COMMIT}")
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=source, text=True
    ).strip()
    if dirty:
        raise ValueError("The registered REINVENT source has tracked modifications")
    sys.path.insert(0, str(source.resolve()))
    import numpy as np
    import torch
    from rdkit import Chem
    from reinvent.chemistry.library_design import attachment_points, bond_maker
    from reinvent.models.libinvent.models.dataset import Dataset
    from reinvent.models.libinvent.models.model import DecoratorModel

    started = time.perf_counter()
    count = int(request["raw_proposal_count"])
    seed = int(request["seed"])
    if not 2 <= count <= 256:
        raise ValueError("LibInvent raw_proposal_count must be between 2 and 256")
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    # torch's legacy pickle loader is permitted only after the exact known hash.
    saved = torch.load(checkpoint, map_location="cpu", weights_only=False)
    if saved.get("model_type") != "Libinvent":
        raise ValueError("Checkpoint is not the registered LibInvent prior")
    model = DecoratorModel.create_from_dict(saved, "inference", torch.device("cpu"))
    scaffold = attachment_points.remove_attachment_point_numbers(request["scaffold"])
    dataset = Dataset(
        [scaffold] * count,
        model.vocabulary.scaffold_vocabulary,
        model.vocabulary.scaffold_tokenizer,
    )
    if len(dataset) != count:
        raise ValueError("The registered scaffold is outside this model vocabulary")
    tensors = Dataset.collate_fn([dataset[i] for i in range(count)])
    sampling_start = time.perf_counter()
    with torch.inference_mode():
        inputs, decorations, likelihoods = model.sample_decorations(*tensors)
    sampling_seconds = time.perf_counter() - sampling_start
    records = []
    for index, (scaffold_input, decoration, likelihood) in enumerate(
        zip(inputs, decorations, likelihoods, strict=True)
    ):
        labeled = attachment_points.add_attachment_point_numbers(scaffold_input, canonicalize=False)
        mol = bond_maker.join_scaffolds_and_decorations(
            labeled, decoration, keep_labels_on_atoms=False
        )
        if mol is not None:
            for atom in mol.GetAtoms():
                atom.SetAtomMapNum(0)
        records.append(
            {
                "name": f"Generated {index + 1}",
                "smiles": Chem.MolToSmiles(mol, isomericSmiles=True) if mol is not None else None,
                "valid": mol is not None,
                "decoration": decoration,
                "model_nll": float(likelihood),
                "proposal_index": index,
            }
        )
    return {
        "records": records,
        "source": "libinvent",
        "seed": seed,
        "checkpoint_sha256": digest,
        "source_commit": commit,
        "versions": {
            package: importlib.metadata.version(package)
            for package in ["torch", "rdkit", "numpy", "molvs"]
        },
        "sampling_seconds": sampling_seconds,
        "seconds": time.perf_counter() - started,
        "limitation": "Scaffold-conditioned graph sampling; "
        "no receptor input or objective training. NLL is not affinity.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(json.loads(args.input.read_text()))
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
