"""Parent-guided RDKit conformers, preserving the calibrated FEgrow procedure.

Adapted from FEgrow conformers.py at 55fd15b2a65df0d64cc30d9eb4684ec5224ddd47.
Only the mapped-atom constrained-embedding capability is used. This is not the
FEgrow model/force-field pipeline, and tethers are released before Vina refinement.

MIT License, Copyright (c) 2022 Daniel J Cole
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, NotRequired, TypedDict

import numpy as np
from numpy.typing import NDArray
from rdkit import Chem
from rdkit.Chem import AllChem


class ConformerRecord(TypedDict):
    molecule: Chem.Mol
    positions: NDArray[np.float64]
    attempt: int
    seed: int


class AttemptIdentity(TypedDict):
    attempt: int
    seed: int


class EmbeddingOutcome(AttemptIdentity):
    status: Literal["generated", "duplicate", "failed"]
    duplicate_conformer: NotRequired[int]
    conformer_index: NotRequired[int]
    error: NotRequired[str]


def generate(
    molecule: Chem.Mol,
    parent: Chem.Mol,
    mapping: Sequence[int],
    attempts: int,
    seed: int,
    minimum_rms: float = 0.5,
) -> tuple[list[ConformerRecord], list[EmbeddingOutcome]]:
    """Return each distinct pose and every failed/duplicate embedding attempt."""
    ligand = Chem.AddHs(Chem.Mol(molecule))
    ligand.RemoveAllConformers()
    parent_xyz = parent.GetConformer()
    coordinates = {
        target: parent_xyz.GetAtomPosition(source) for source, target in enumerate(mapping)
    }
    alignment = [(target, source) for source, target in enumerate(mapping)]
    kept: list[ConformerRecord] = []
    outcomes: list[EmbeddingOutcome] = []
    heavy_indices = [atom.GetIdx() for atom in ligand.GetAtoms() if atom.GetAtomicNum() > 1]
    for index in range(attempts):
        attempt_seed = seed + index
        try:
            pose = Chem.Mol(ligand)
            conformer_id = AllChem.EmbedMolecule(
                pose,
                coordMap=coordinates,
                randomSeed=attempt_seed,
                useExpTorsionAnglePrefs=True,
                useBasicKnowledge=True,
                enforceChirality=True,
                useSmallRingTorsions=True,
            )
            if conformer_id < 0:
                raise ValueError("RDKit could not embed this attempt")
            AllChem.AlignMol(pose, parent, atomMap=alignment)
            force_field = AllChem.UFFGetMoleculeForceField(pose, confId=0)
            if force_field is None:
                raise ValueError("UFF does not support this candidate")
            for source, target in enumerate(mapping):
                p = parent_xyz.GetAtomPosition(source)
                point = force_field.AddExtraPoint(p.x, p.y, p.z, fixed=True) - 1
                force_field.AddDistanceConstraint(point, target, 0, 0, 10000.0)
            force_field.Initialize()
            for _ in range(5):
                if not force_field.Minimize(energyTol=1e-4, forceTol=1e-3):
                    break
            AllChem.AlignMol(pose, parent, atomMap=alignment)
            positions = pose.GetConformer().GetPositions()[heavy_indices]
            duplicate = next(
                (
                    i
                    for i, item in enumerate(kept)
                    if float(np.sqrt(np.mean(np.sum((positions - item["positions"]) ** 2, axis=1))))
                    < minimum_rms
                ),
                None,
            )
            if duplicate is not None:
                outcomes.append(
                    {
                        "attempt": index,
                        "seed": attempt_seed,
                        "status": "duplicate",
                        "duplicate_conformer": duplicate,
                    }
                )
                continue
            Chem.AssignStereochemistryFrom3D(pose, confId=0, replaceExistingTags=True)
            if not Chem.RemoveHs(pose).HasSubstructMatch(molecule, useChirality=True):
                raise ValueError("Embedding changed explicitly specified stereochemistry")
            kept.append(
                {"molecule": pose, "positions": positions, "attempt": index, "seed": attempt_seed}
            )
            outcomes.append(
                {
                    "attempt": index,
                    "seed": attempt_seed,
                    "status": "generated",
                    "conformer_index": len(kept) - 1,
                }
            )
        except Exception as exc:
            outcomes.append(
                {"attempt": index, "seed": attempt_seed, "status": "failed", "error": str(exc)}
            )
    return kept, outcomes
