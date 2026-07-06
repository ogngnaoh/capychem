"""The ScoringOracle protocol — the pluggable scoring seam (07-03).

A ``ScoringOracle`` turns a batch of SMILES into a batch of scalar scores (``None``
for a molecule it cannot score). It carries enough metadata to be ranked and cited:
a ``name``, a ``version`` (provenance / OD-5), and a ``direction`` so a
``minimize`` oracle is never silently ranked as if higher were better.

Consumed at the objective boundary (07-04) and by the trust/quality layer (07-05);
07-03 ships the protocol + registry + presets, proven at parity, without rewiring
the loop. Keep the surface small — richer capabilities (applicability domain / a
canary probe) are additive in 07-05.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

Direction = Literal["maximize", "minimize"]


@runtime_checkable
class ScoringOracle(Protocol):
    """Structural type for a pluggable scoring function.

    ``score`` returns one value per input SMILES, in order, ``None`` where the
    molecule is invalid or out of the oracle's domain. Implementations MUST be
    deterministic for a given input (G6) — the loop and the eval metric both rely
    on stable scores.

    ``name``/``version``/``direction`` are read-only properties so a *frozen* value
    object (a descriptor oracle) satisfies the protocol just as a plain-attribute
    class (PmoOracle) does — a read-write attribute is a valid implementation of a
    read-only member, but not vice-versa.
    """

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def direction(self) -> Direction: ...

    def score(self, smiles: list[str]) -> list[float | None]: ...
