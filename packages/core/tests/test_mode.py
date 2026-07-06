"""derive_mode: the benchmark/exploratory invariant carrier (milestone 07 slice 01).

Any custom seed / objective / constraint ⇒ exploratory; nothing custom ⇒ benchmark.
Mode is server-derived from these inputs, never client-set — this is the single
function every later 07 feature routes its inputs through so the G1 benchmark path
stays pristine.
"""

from __future__ import annotations

from capychem.mode import derive_mode


def test_no_custom_inputs_is_benchmark() -> None:
    assert derive_mode() == "benchmark"
    assert derive_mode(objective_json=None, constraints_json=None, seed_smiles=None) == "benchmark"


def test_seed_smiles_forces_exploratory() -> None:
    assert derive_mode(seed_smiles=["CCO"]) == "exploratory"


def test_objective_json_forces_exploratory() -> None:
    assert derive_mode(objective_json={"components": [{"oracle": "qed", "weight": 1.0}]}) == (
        "exploratory"
    )


def test_constraints_json_forces_exploratory() -> None:
    assert derive_mode(constraints_json={"exclude": ["[#7]"]}) == "exploratory"


def test_empty_custom_inputs_stay_benchmark() -> None:
    # An empty seed list / empty objective / empty constraints is "no custom input",
    # not a degenerate exploratory run — a client sending [] or {} must not silently
    # drop a run out of the benchmark denominator.
    assert derive_mode(seed_smiles=[]) == "benchmark"
    assert derive_mode(objective_json={}) == "benchmark"
    assert derive_mode(constraints_json={}) == "benchmark"


def test_any_single_custom_input_is_enough() -> None:
    # A benchmark tag is impossible the moment ANY exploratory feature is present.
    assert derive_mode(seed_smiles=["CCO"], objective_json=None) == "exploratory"
    assert derive_mode(objective_json={"components": []}, seed_smiles=None) == "exploratory"
