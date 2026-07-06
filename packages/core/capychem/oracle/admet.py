"""ADMET-AI oracle (07-03) — an OPTIONAL preset, import-guarded.

ADMET-AI (`admet_ai`, MIT, CPU-friendly) is a heavy optional dependency: the stub /
benchmark path must never need it. This module always imports cleanly; the model is
loaded lazily on first score, and the registry only registers ADMET oracles when
``admet_available()`` is true. Correctness of the predictions is ADMET-AI's (N5).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Any

from capychem.oracle.protocol import Direction

# A few common ADMET-AI endpoints with their optimization direction. Kept small and
# explicit; the point in 07-03 is the plug, not endpoint coverage.
_ENDPOINTS: dict[str, Direction] = {
    "solubility_aqsoldb": "maximize",  # log(mol/L) — higher aqueous solubility
    "hia_hou": "maximize",  # human intestinal absorption probability
    "bbb_martins": "maximize",  # blood-brain-barrier penetration probability
}


def admet_available() -> bool:
    """True when the optional ``admet_ai`` package is importable."""
    try:
        import admet_ai  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _model() -> Any:
    """Lazily construct the ADMET-AI model once (heavy: weights + featurizers)."""
    from admet_ai import ADMETModel

    return ADMETModel()


class AdmetOracle:
    """One ADMET-AI endpoint behind the ScoringOracle protocol. Invalid SMILES score
    ``None``; the model is loaded on first ``score``, never at import."""

    version = "admet_ai"

    def __init__(self, endpoint: str, direction: Direction) -> None:
        self.endpoint = endpoint
        self.name = f"admet:{endpoint}"
        self.direction = direction

    def score(self, smiles: list[str]) -> list[float | None]:
        from rdkit import Chem

        valid_idx = [i for i, s in enumerate(smiles) if Chem.MolFromSmiles(s) is not None]
        out: list[float | None] = [None] * len(smiles)
        if not valid_idx:
            return out
        preds = _model().predict(smiles=[smiles[i] for i in valid_idx])
        col = preds[self.endpoint]
        for i, val in zip(valid_idx, col.tolist(), strict=True):
            out[i] = float(val)
        return out


def register_admet_oracles(register: Callable[[str, Callable[..., Any]], None]) -> None:
    """Register the bundled ADMET endpoints — a no-op if ``admet_ai`` is absent, so
    the registry stays clean on the stub/benchmark path."""
    if not admet_available():
        return
    for endpoint, direction in _ENDPOINTS.items():
        register(f"admet:{endpoint}", lambda ep=endpoint, d=direction: AdmetOracle(ep, d))
