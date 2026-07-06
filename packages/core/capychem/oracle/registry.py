"""Oracle registry — name → factory, with the bundled presets registered at load.

``get_oracle(name, **kwargs)`` builds a fresh oracle; ``pmo`` needs a ``task``
kwarg, the descriptor presets take none. ADMET-AI endpoints register only when the
optional dependency is present (import-guarded), so the stub/benchmark path never
pulls it in.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from capychem.oracle import admet, descriptors
from capychem.oracle.pmo import PmoOracle
from capychem.oracle.protocol import ScoringOracle

_FACTORIES: dict[str, Callable[..., ScoringOracle]] = {}


def register_oracle(name: str, factory: Callable[..., ScoringOracle]) -> None:
    """Register (or replace) an oracle factory under ``name``."""
    _FACTORIES[name] = factory


def get_oracle(name: str, **kwargs: Any) -> ScoringOracle:
    """Build the named oracle. Raises ``KeyError`` for an unknown name so a typo
    fails loudly rather than silently scoring against the wrong thing."""
    if name not in _FACTORIES:
        raise KeyError(f"Unknown oracle {name!r}; available: {available_oracles()}")
    return _FACTORIES[name](**kwargs)


def available_oracles() -> list[str]:
    return sorted(_FACTORIES)


register_oracle("pmo", PmoOracle)
register_oracle("qed", descriptors.qed_oracle)
register_oracle("sa_score", descriptors.sa_score_oracle)
register_oracle("mw", descriptors.mol_weight_oracle)
register_oracle("clogp", descriptors.clogp_oracle)
register_oracle("tpsa", descriptors.tpsa_oracle)
admet.register_admet_oracles(register_oracle)
