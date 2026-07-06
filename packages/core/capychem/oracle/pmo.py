"""PmoOracle — the PMO/PyTDC benchmark oracle behind the ScoringOracle protocol.

Thin wrapper over the harness bridge (``score_smiles``): it exposes the exact
benchmark scores through the protocol so the objective boundary (07-04) can treat
PMO as one oracle among many WITHOUT changing the G1 numbers. A parity test proves
``PmoOracle(task).score`` is byte-identical to the harness path.
"""

from __future__ import annotations

from capychem.oracle import score_smiles
from capychem.oracle.protocol import Direction

# The pinned legacy harness (CLAUDE.md / SPEC §5). Static for now; OD-5 (07-06)
# makes the harness emit the real PyTDC version so the manifest cites it dynamically.
_PYTDC_PIN = "pytdc-0.3.6"


class PmoOracle:
    """A single PMO task scored via the isolated harness. Direction is ``maximize``
    (every PMO oracle returns a score in [0, 1] where higher is better)."""

    direction: Direction = "maximize"

    def __init__(self, task: str) -> None:
        self.task = task
        self.name = f"pmo:{task}"
        self.version = _PYTDC_PIN

    def score(self, smiles: list[str]) -> list[float | None]:
        # Delegates to the one sanctioned harness crossing; no reordering, no
        # transform — the returned scores ARE the benchmark scores.
        return [r.score for r in score_smiles(smiles, self.task)]
