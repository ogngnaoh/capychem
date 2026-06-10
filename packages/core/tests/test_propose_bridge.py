"""Integration test of the Graph-GA proposer over the real harness bridge.

Exercises the real harness venv (Python 3.10) via subprocess — no mocking.
Proves determinism (G6, slice-local): same seed -> identical offspring + parents.
"""

from __future__ import annotations

from capychem.oracle import Offspring, propose_offspring

_POP = [("CCO", 0.40), ("c1ccccc1", 0.60), ("CCN", 0.50), ("CCOC", 0.55)]


def test_propose_returns_offspring_with_parent_indices() -> None:
    out = propose_offspring(_POP, n_offspring=8, mutation_rate=0.01, seed=42)
    assert all(isinstance(o, Offspring) for o in out)
    assert len(out) <= 8  # may be fewer: crossover can fail
    for o in out:
        assert isinstance(o.smiles, str) and o.smiles
        i, j = o.parents
        assert 0 <= i < len(_POP) and 0 <= j < len(_POP)


def test_propose_is_deterministic_for_same_seed() -> None:
    a = propose_offspring(_POP, n_offspring=8, mutation_rate=0.01, seed=42)
    b = propose_offspring(_POP, n_offspring=8, mutation_rate=0.01, seed=42)
    assert [(o.smiles, o.parents) for o in a] == [(o.smiles, o.parents) for o in b]
