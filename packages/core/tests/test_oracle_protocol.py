"""Slice 07-03: pluggable ScoringOracle protocol + registry + presets.

The benchmark path is protected by a parity test — PmoOracle must reproduce the
harness scores byte-for-byte. Direction is honored (a minimize oracle isn't
silently ranked as if higher were better).
"""

from __future__ import annotations

import pytest
from capychem.loop.logic import merge_and_truncate
from capychem.loop.state import Scored
from capychem.oracle import descriptors  # noqa: F401  (ensures the module imports)
from capychem.oracle.pmo import PmoOracle
from capychem.oracle.protocol import ScoringOracle
from capychem.oracle.registry import available_oracles, get_oracle

# --- registry -----------------------------------------------------------------


def test_registry_lists_bundled_presets() -> None:
    names = available_oracles()
    assert {"pmo", "qed", "sa_score", "mw", "clogp", "tpsa"} <= set(names)


def test_get_unknown_oracle_raises() -> None:
    with pytest.raises(KeyError, match="Unknown oracle"):
        get_oracle("does_not_exist")


def test_pmo_oracle_via_registry_needs_task() -> None:
    o = get_oracle("pmo", task="qed")
    assert o.name == "pmo:qed"
    assert o.direction == "maximize"


def test_bundled_oracles_satisfy_the_protocol() -> None:
    for name in ("qed", "sa_score", "mw", "clogp", "tpsa"):
        assert isinstance(get_oracle(name), ScoringOracle)


# --- PMO parity (the benchmark-preserving guarantee) --------------------------


def test_pmo_oracle_scores_are_byte_identical_to_score_smiles() -> None:
    from capychem.oracle import score_smiles

    smis = ["CCO", "c1ccccc1", "CCN"]
    expected = [r.score for r in score_smiles(smis, "qed")]
    assert PmoOracle("qed").score(smis) == expected


# --- descriptor oracles (zero new deps) ---------------------------------------


def test_qed_descriptor_is_maximize_and_bounded() -> None:
    o = get_oracle("qed")
    assert o.direction == "maximize"
    scores = o.score(["CCO", "not-a-smiles"])
    assert scores[0] is not None and 0.0 <= scores[0] <= 1.0
    assert scores[1] is None  # invalid SMILES -> None, never trusted


def test_sa_score_descriptor_is_minimize() -> None:
    o = get_oracle("sa_score")
    assert o.direction == "minimize"  # lower SA = easier to synthesize
    scores = o.score(["CCO"])
    assert scores[0] is not None and scores[0] > 0


def test_admet_is_import_guarded() -> None:
    # The optional ADMET-AI dep must never break the stub/benchmark path: the module
    # imports cleanly, reports availability, and registers nothing when it's absent.
    from capychem.oracle import admet

    assert isinstance(admet.admet_available(), bool)
    if not admet.admet_available():
        assert not any(n.startswith("admet:") for n in available_oracles())


# --- direction threading ------------------------------------------------------


def test_merge_and_truncate_maximize_default_is_unchanged() -> None:
    pop = [Scored("A", 0.9), Scored("B", 0.1)]
    assert merge_and_truncate([], pop, pop_size=1)[0].smiles == "A"


def test_merge_and_truncate_minimize_flips_ranking() -> None:
    pop = [Scored("A", 0.9), Scored("B", 0.1)]
    assert merge_and_truncate([], pop, pop_size=1, direction="minimize")[0].smiles == "B"
