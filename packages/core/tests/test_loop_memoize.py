"""The score node memoizes by canonical SMILES so the budget counts UNIQUE calls (slice 05)."""

from __future__ import annotations

from typing import Any

from capychem.loop import graph as graph_mod
from capychem.oracle import OracleResult
from capychem.validate import ValidCandidate


def _score_state(
    validated: list[ValidCandidate], *, buffer: set[str], budget: int
) -> dict[str, Any]:
    return {
        "validated": validated,
        "_fallback_validated": [],
        "mol_buffer": buffer,
        "budget": budget,
        "task": "qed",
        "run_trace_id": None,
        "gen_span_id": None,
    }


async def test_score_skips_cross_generation_duplicates(monkeypatch) -> None:
    scored_batches: list[list[str]] = []

    async def fake_score(smiles, task):
        scored_batches.append(list(smiles))
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0)
            for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    state = _score_state(
        [
            ValidCandidate("CCO", None),
            ValidCandidate("CCN", None),
            ValidCandidate("c1ccccc1", None),
        ],
        buffer={"CCO"},  # CCO already scored by a prior generation
        budget=10,
    )
    out = await graph_mod.score(state)  # type: ignore[arg-type]
    assert scored_batches == [["CCN", "c1ccccc1"]]          # CCO not sent to the oracle
    assert out["calls_used"] == 3                            # {CCO} + 2 new
    assert out["mol_buffer"] == {"CCO", "CCN", "c1ccccc1"}
    # cache hit not persisted
    assert {c.smiles for c, _, _ in out["_scored"]} == {"CCN", "c1ccccc1"}


async def test_score_caps_unseen_to_unique_headroom(monkeypatch) -> None:
    scored_batches: list[list[str]] = []

    async def fake_score(smiles, task):
        scored_batches.append(list(smiles))
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0)
            for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    state = _score_state(
        [
            ValidCandidate("CCN", None),
            ValidCandidate("c1ccccc1", None),
            ValidCandidate("CCC", None),
        ],
        buffer={"CCO"},  # 1 unique call already used
        budget=2,        # room = 2 - 1 = 1
    )
    out = await graph_mod.score(state)  # type: ignore[arg-type]
    assert scored_batches == [["CCN"]]                       # only one unseen fits the headroom
    assert out["calls_used"] == 2
    assert out["mol_buffer"] == {"CCO", "CCN"}


async def test_score_no_headroom_scores_nothing(monkeypatch) -> None:
    async def fake_score(smiles, task):
        raise AssertionError("must not score when the unique budget is exhausted")

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    state = _score_state([ValidCandidate("CCN", None)], buffer={"CCO", "CCC"}, budget=2)
    out = await graph_mod.score(state)  # type: ignore[arg-type]
    assert out["_scored"] == []
    assert out["calls_used"] == 2
    assert out["mol_buffer"] == {"CCO", "CCC"}
