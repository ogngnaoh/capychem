"""Slice 07-04: the score node evaluates a composed objective when one is present,
and is byte-identical to the benchmark path when it is absent.
"""

from __future__ import annotations

from typing import Any

import pytest
from capychem.loop import graph as graph_mod
from capychem.objective import apply_transform
from capychem.oracle import OracleResult
from capychem.validate import ValidCandidate


def _score_state(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_id": 1,
        "gen_index": 1,
        "task": "qed",
        "budget": 100,
        "validated": [ValidCandidate("CCO", None), ValidCandidate("CCN", None)],
        "mol_buffer": set(),
        "run_trace_id": None,
        "gen_span_id": None,
    }
    base.update(over)
    return base


def _fake_results(smiles: list[str], score: float, cost: float) -> list[OracleResult]:
    return [
        OracleResult(smiles=s, score=score, valid=True, wall_ms=1, cost_usd=cost) for s in smiles
    ]


async def test_score_node_uses_objective_when_present(monkeypatch) -> None:
    async def fake_sba(smiles: list[str], task: str) -> list[OracleResult]:
        return _fake_results(smiles, 0.5, 0.02)

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_sba)
    # A sigmoid transform maps the raw 0.5 to something != 0.5, so this fails unless
    # the score node actually routes through the objective (not the raw benchmark path).
    transform = {"kind": "sigmoid", "low": 0.5, "high": 1.5, "k": 10.0}
    objective_json = {
        "terms": [
            {"oracle": "pmo", "oracle_kwargs": {"task": "qed"}, "weight": 1.0,
             "transform": transform},
        ],
        "aggregator": "weighted_sum",
    }
    out = await graph_mod.score(_score_state(objective_json=objective_json))  # type: ignore[arg-type]
    scored = out["_scored"]
    assert len(scored) == 2
    expected = apply_transform(transform, 0.5)
    assert expected != pytest.approx(0.5)  # the transform genuinely moves the value
    assert scored[0][1] == pytest.approx(expected)  # objective path applied the transform
    assert scored[0][2] == 0.02  # PMO term cost carried through


async def test_score_node_benchmark_path_unchanged_without_objective(monkeypatch) -> None:
    async def fake_sba(smiles: list[str], task: str) -> list[OracleResult]:
        return _fake_results(smiles, 0.7, 0.03)

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_sba)
    out = await graph_mod.score(_score_state())  # no objective_json
    scored = out["_scored"]
    assert [s[1] for s in scored] == [0.7, 0.7]
    assert [s[2] for s in scored] == [0.03, 0.03]
