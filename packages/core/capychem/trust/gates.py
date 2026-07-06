"""Shared trust gates (07-05) — one home for the reward-hacking defenses.

Unifies the ``PARSE_RATE_FLOOR`` that ``eval/beat.py`` and ``eval/verdict.py`` each
carried a private copy of, re-exports the valid-SMILES gate, and adds a custom-oracle
**canary**: score a fixed set of degenerate probe molecules and warn if the oracle
rates them implausibly high — the classic sign a pluggable oracle is mis-specified or
reward-hackable before an exploratory run trusts it.
"""

from __future__ import annotations

from dataclasses import dataclass

from capychem.loop.logic import valid_smiles_gate
from capychem.oracle.protocol import ScoringOracle

__all__ = ["PARSE_RATE_FLOOR", "CanaryResult", "oracle_canary", "valid_smiles_gate"]

# Below this analyzer-parse-rate the reasoning-mode chain-of-thought is crowding out
# the {focus, avoid} JSON, so a null hypothesis is untrustworthy and the with/without
# analyzer AUC delta is not a true comparison. Single source (was duplicated).
PARSE_RATE_FLOOR = 0.8

# Degenerate probes: trivially small / pathological molecules a well-specified oracle
# should score LOW. An oracle that rates these near 1.0 is almost certainly gameable.
_CANARY_PROBES = ["C", "CC", "CCC", "O", "N", "C=O", "CO", "[Na+].[Cl-]"]

_CANARY_THRESHOLD = 0.9


@dataclass(frozen=True)
class CanaryResult:
    suspicious: bool
    max_score: float | None
    probe_scores: dict[str, float | None]


def oracle_canary(oracle: ScoringOracle, threshold: float = _CANARY_THRESHOLD) -> CanaryResult:
    """Score the degenerate probe set; flag the oracle ``suspicious`` when any probe
    scores at or above ``threshold`` (a well-specified maximize oracle scores trivial
    molecules low)."""
    scores = oracle.score(_CANARY_PROBES)
    present = [s for s in scores if s is not None]
    max_score = max(present) if present else None
    return CanaryResult(
        suspicious=max_score is not None and max_score >= threshold,
        max_score=max_score,
        probe_scores=dict(zip(_CANARY_PROBES, scores, strict=True)),
    )
