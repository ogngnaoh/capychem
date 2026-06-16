"""Modern-RDKit SMILES validation + canonicalization (Python 3.12 side).

Runs before any oracle call: invalid SMILES are dropped and intra-batch
duplicates collapsed by canonical form, so the budget is never spent on junk
(FR-004). The harness scores; this gate decides what reaches it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from rdkit import Chem, RDLogger

# Silence per-molecule parse warnings; invalidity is signalled by a None mol.
RDLogger.DisableLog("rdApp.*")


@dataclass(frozen=True)
class ValidCandidate:
    """A canonicalized, unique candidate that survived validation.

    ``parents`` carries the proposer's provenance forward (None at gen 0).
    """

    smiles: str  # canonical SMILES
    parents: tuple[int, int] | None


@dataclass(frozen=True)
class ValidationStats:
    """Per-batch parse-validity counts.

    ``valid`` counts RDKit-parseable inputs BEFORE intra-batch dedup, so ``rate``
    measures validity (can RDKit parse it), not novelty. This is the per-run
    valid-SMILES signal milestone 02's >80% gate compares against.
    """

    proposed: int
    valid: int

    @property
    def rate(self) -> float:
        return self.valid / self.proposed if self.proposed else 0.0


def canonicalize(smiles: str) -> str | None:
    """Return canonical SMILES, or None if RDKit cannot parse it."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return cast(str, Chem.MolToSmiles(mol))


def validate_batch_with_stats(
    candidates: list[tuple[str, tuple[int, int] | None]],
) -> tuple[list[ValidCandidate], ValidationStats]:
    """Like :func:`validate_batch`, but also report parse-validity stats.

    ``valid`` is incremented for every RDKit-parseable input, before the dedup
    filter — so a repeated-but-valid molecule still counts as valid.
    """
    seen: set[str] = set()
    out: list[ValidCandidate] = []
    valid = 0
    for raw, parents in candidates:
        canon = canonicalize(raw)
        if canon is None:
            continue
        valid += 1
        if canon in seen:
            continue
        seen.add(canon)
        out.append(ValidCandidate(smiles=canon, parents=parents))
    return out, ValidationStats(proposed=len(candidates), valid=valid)


def validate_batch(
    candidates: list[tuple[str, tuple[int, int] | None]],
) -> list[ValidCandidate]:
    """Canonicalize, drop invalid, collapse intra-batch duplicates.

    ``candidates`` is a list of (raw_smiles, parents) pairs. The first occurrence
    of each canonical form wins (keeping its provenance). Input order is
    preserved — deterministic for G6.
    """
    out, _ = validate_batch_with_stats(candidates)
    return out
