"""Zero-new-dependency descriptor oracles (07-03).

RDKit-native physicochemical scorers usable as ScoringOracles. QED (drug-likeness,
maximize) and SA-score (synthetic accessibility, minimize) have canonical
directions; MW / clogP / TPSA are band-oriented — their standalone ``direction`` is
a documented drug-likeness *convention* (smaller / less-lipophilic preferred, all
else equal), and a real objective should compose them with a band transform (07-04)
rather than optimize them raw. Correctness of the underlying descriptors is RDKit's
(PRD N5); this module only wires them to the protocol.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from capychem.oracle.protocol import Direction
from rdkit import Chem
from rdkit.Chem import QED, Crippen, Descriptors, RDConfig, rdMolDescriptors

# SA-score lives in RDKit's Contrib tree, not the importable package; add it to the
# path once at module load (the standard RDKit recipe).
sys.path.append(os.path.join(RDConfig.RDContribDir, "SA_Score"))
import sascorer  # type: ignore[import-not-found]  # noqa: E402  (path appended above)

_RDKIT_VERSION = f"rdkit-{Chem.rdBase.rdkitVersion}"


@dataclass(frozen=True)
class DescriptorOracle:
    """A ScoringOracle backed by a pure RDKit ``mol -> float`` function. Invalid
    SMILES score ``None`` (never trusted as a value)."""

    name: str
    direction: Direction
    fn: Callable[[Any], float]
    version: str = _RDKIT_VERSION

    def score(self, smiles: list[str]) -> list[float | None]:
        out: list[float | None] = []
        for smi in smiles:
            mol = Chem.MolFromSmiles(smi)
            out.append(None if mol is None else float(self.fn(mol)))
        return out


def qed_oracle() -> DescriptorOracle:
    return DescriptorOracle(name="qed", direction="maximize", fn=QED.qed)


def sa_score_oracle() -> DescriptorOracle:
    return DescriptorOracle(name="sa_score", direction="minimize", fn=sascorer.calculateScore)


def mol_weight_oracle() -> DescriptorOracle:
    return DescriptorOracle(name="mw", direction="minimize", fn=Descriptors.MolWt)


def clogp_oracle() -> DescriptorOracle:
    return DescriptorOracle(name="clogp", direction="minimize", fn=Crippen.MolLogP)


def tpsa_oracle() -> DescriptorOracle:
    return DescriptorOracle(name="tpsa", direction="minimize", fn=rdMolDescriptors.CalcTPSA)
