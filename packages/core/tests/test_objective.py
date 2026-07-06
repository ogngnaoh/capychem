"""Slice 07-04: composed multi-term objective -> one scalar in [0,1].

Transforms map a raw oracle value into [0,1]; the aggregator combines weighted terms
into [0,1] by construction (so AUC stays comparable). A single identity term equals
the raw oracle. PMO terms reuse the loop's harness scorer (injected) so the benchmark
path is untouched; descriptor terms score locally for free.
"""

from __future__ import annotations

import pytest
from capychem.objective import Objective, ObjectiveSpec, apply_transform
from capychem.oracle import OracleResult

# --- transforms map into [0,1] ------------------------------------------------


def test_identity_passes_through_and_clamps() -> None:
    assert apply_transform({"kind": "identity"}, 0.4) == pytest.approx(0.4)
    assert apply_transform({"kind": "identity"}, 1.5) == 1.0  # clamped
    assert apply_transform({"kind": "identity"}, -0.2) == 0.0


def test_sigmoid_is_monotonic_and_bounded() -> None:
    t = {"kind": "sigmoid", "low": 0.0, "high": 10.0, "k": 10.0}
    lo, mid, hi = apply_transform(t, 0.0), apply_transform(t, 5.0), apply_transform(t, 10.0)
    assert 0.0 <= lo < mid < hi <= 1.0
    assert mid == pytest.approx(0.5, abs=1e-6)  # midpoint -> 0.5


def test_reverse_sigmoid_inverts_direction() -> None:
    t = {"kind": "reverse_sigmoid", "low": 0.0, "high": 10.0, "k": 10.0}
    assert apply_transform(t, 0.0) > apply_transform(t, 10.0)  # lower raw -> higher score


def test_double_sigmoid_peaks_in_band() -> None:
    t = {"kind": "double_sigmoid", "low": 2.0, "high": 4.0, "k": 10.0}
    inside, below, above = apply_transform(t, 3.0), apply_transform(t, 0.0), apply_transform(t, 6.0)
    assert inside > below and inside > above


# --- aggregation stays in [0,1]; single term == raw ---------------------------


def _spec(terms: list[dict], aggregator: str = "weighted_sum") -> ObjectiveSpec:
    return ObjectiveSpec.from_json({"terms": terms, "aggregator": aggregator})


def test_single_identity_term_equals_raw_oracle() -> None:
    for agg in ("weighted_sum", "weighted_product"):
        spec = _spec([{"oracle": "qed", "weight": 1.0, "transform": {"kind": "identity"}}], agg)
        # aggregate of one identity term is just the raw [0,1] value
        assert spec.aggregate([0.73], [1.0]) == pytest.approx(0.73)


def test_weighted_sum_and_product_stay_in_unit_interval() -> None:
    spec = _spec(
        [
            {"oracle": "qed", "weight": 2.0, "transform": {"kind": "identity"}},
            {"oracle": "sa_score", "weight": 1.0, "transform": {"kind": "identity"}},
        ]
    )
    v = spec.aggregate([0.8, 0.2], [2.0, 1.0])
    assert 0.0 <= v <= 1.0
    assert v == pytest.approx((2 * 0.8 + 1 * 0.2) / 3)


# --- evaluate_async: injected PMO scorer + descriptor term --------------------


async def test_evaluate_composes_pmo_and_descriptor_with_cost() -> None:
    spec_json = {
        "terms": [
            {"oracle": "pmo", "oracle_kwargs": {"task": "qed"}, "weight": 1.0,
             "transform": {"kind": "identity"}},
            {"oracle": "qed", "weight": 1.0, "transform": {"kind": "identity"}},
        ],
        "aggregator": "weighted_sum",
    }
    objective = Objective.from_json(spec_json)

    async def stub_pmo(smiles: list[str], task: str) -> list[OracleResult]:
        # deterministic fake harness scores + a per-call cost
        return [
            OracleResult(smiles=s, score=0.6, valid=True, wall_ms=1, cost_usd=0.01) for s in smiles
        ]

    out = await objective.evaluate_async(["CCO", "c1ccccc1"], pmo_scorer=stub_pmo)
    assert len(out) == 2
    assert all(r.score is not None and 0.0 <= r.score <= 1.0 for r in out)
    assert out[0].cost_usd == pytest.approx(0.01)  # PMO term costs; descriptor is free


async def test_evaluate_returns_none_when_any_term_is_none() -> None:
    spec_json = {
        "terms": [{"oracle": "qed", "weight": 1.0, "transform": {"kind": "identity"}}],
        "aggregator": "weighted_sum",
    }
    objective = Objective.from_json(spec_json)

    async def stub_pmo(smiles: list[str], task: str) -> list[OracleResult]:
        raise AssertionError("no pmo term here")

    out = await objective.evaluate_async(["not-a-smiles"], pmo_scorer=stub_pmo)
    assert out[0].score is None  # invalid SMILES -> qed None -> objective None


def test_objective_json_round_trips() -> None:
    spec_json = {
        "terms": [{"oracle": "qed", "oracle_kwargs": {}, "weight": 1.0,
                   "transform": {"kind": "identity"}}],
        "aggregator": "weighted_product",
    }
    assert Objective.from_json(spec_json).to_json() == spec_json
