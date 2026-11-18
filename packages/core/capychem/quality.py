"""Per-candidate molecule-quality report (07-05) — the reward-hacking defense.

A high oracle score on a degenerate or unsynthesizable molecule is the classic
reward-hacking failure. Every persisted candidate carries a cheap, RDKit-native
quality report (synthesizability, drug-likeness, structural alarms) so a reviewer can
see WHAT the optimizer actually produced. Annotate-only (OD-4): computing quality never
drops a candidate, so a benchmark run's top-10 is unchanged. Correctness of the
descriptors is RDKit's."""

from __future__ import annotations

import os
import sys
from typing import Any

from rdkit import Chem, DataStructs
from rdkit.Chem import (
    QED,
    Crippen,
    Descriptors,
    Lipinski,
    RDConfig,
    rdFingerprintGenerator,
    rdMolDescriptors,
)
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

sys.path.append(os.path.join(RDConfig.RDContribDir, "SA_Score"))
import sascorer  # type: ignore[import-not-found]  # noqa: E402  (path appended above)

# Non-deprecated Morgan generator (the old GetMorganFingerprintAsBitVect warns).
_MORGAN = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


def _catalog(which: FilterCatalogParams.FilterCatalogs) -> FilterCatalog:
    params = FilterCatalogParams()
    params.AddCatalog(which)
    return FilterCatalog(params)


_PAINS = _catalog(FilterCatalogParams.FilterCatalogs.PAINS)
_BRENK = _catalog(FilterCatalogParams.FilterCatalogs.BRENK)


def molecule_quality(smiles: str) -> dict[str, Any]:
    """A bounded RDKit quality report. Invalid SMILES report ``{"valid": False}`` —
    never trusted as having any quality."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"valid": False}
    mw = float(Descriptors.MolWt(mol))
    logp = float(Crippen.MolLogP(mol))
    hbd = int(Lipinski.NumHDonors(mol))
    hba = int(Lipinski.NumHAcceptors(mol))
    rotb = int(Lipinski.NumRotatableBonds(mol))
    tpsa = float(rdMolDescriptors.CalcTPSA(mol))
    return {
        "valid": True,
        "sa_score": round(float(sascorer.calculateScore(mol)), 3),
        "qed": round(float(QED.qed(mol)), 4),
        "mw": round(mw, 2),
        "logp": round(logp, 3),
        "hbd": hbd,
        "hba": hba,
        "rotatable_bonds": rotb,
        "tpsa": round(tpsa, 2),
        # Lipinski Ro5 + Veber: standard drug-likeness rule-sets (pass = drug-like).
        "lipinski_pass": mw <= 500 and hbd <= 5 and hba <= 10 and logp <= 5,
        "veber_pass": rotb <= 10 and tpsa <= 140,
        # Structural alarms (True = TRIPS the alarm — a liability).
        "pains": bool(_PAINS.HasMatch(mol)),
        "brenk": bool(_BRENK.HasMatch(mol)),
    }


def _fingerprint(smiles: str) -> Any:
    mol = Chem.MolFromSmiles(smiles)
    return None if mol is None else _MORGAN.GetFingerprint(mol)


def internal_diversity(smiles: list[str]) -> float:
    """MOSES-style internal diversity: 1 − mean pairwise Tanimoto over Morgan FPs.
    0.0 for fewer than two valid molecules (nothing to compare)."""
    fps = [f for f in (_fingerprint(s) for s in smiles) if f is not None]
    if len(fps) < 2:
        return 0.0
    total, pairs = 0.0, 0
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            total += DataStructs.TanimotoSimilarity(fps[i], fps[j])
            pairs += 1
    return round(1.0 - total / pairs, 4)


def novelty(smiles: list[str], seed_pop: set[str]) -> float:
    """Fraction of the molecules whose canonical SMILES were NOT in the seed set."""
    if not smiles:
        return 0.0
    return round(sum(1 for s in smiles if s not in seed_pop) / len(smiles), 4)
