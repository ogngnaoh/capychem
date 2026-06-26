"""The propose node selects the proposer by mutation_strategy (slice 04)."""

from __future__ import annotations

from typing import Any

import pytest
from capychem.loop import graph as graph_mod
from capychem.loop.state import Scored


def _gen1_state(strategy_name: str) -> dict[str, Any]:
    return {
        "run_id": 1,
        "gen_index": 1,
        "mutation_strategy": strategy_name,
        "task": "qed",
        "offspring": 3,
        "mutation_rate": 0.01,
        "seed": 42,
        "pop_size": 4,
        "population": [Scored(smiles="CCO", score=0.9), Scored(smiles="CCN", score=0.4)],
        "calls_used": 0,
        "run_trace_id": None,
        "gen_span_id": None,
    }


async def test_propose_graph_ga_uses_ga_fill(monkeypatch) -> None:
    monkeypatch.setattr(
        graph_mod.strategy,
        "ga_fill",
        lambda pop, n, *, mutation_rate, seed: [("CCC", (0, 1))] * n,
    )
    out = await graph_mod.propose(_gen1_state("graph_ga"))  # type: ignore[arg-type]
    assert out["_proposer"] == "graph_ga"
    assert out["proposed"] == [("CCC", (0, 1))] * 3


async def test_propose_llm_returns_raw_strings_parents_none(monkeypatch) -> None:
    from capychem.proposer import ProposalResult

    async def fake_llm(task, population, *, n, seed):
        return [
            ProposalResult(raw="CCO", smiles="CCO", tokens_in=1, tokens_out=2) for _ in range(n)
        ]

    monkeypatch.setattr(graph_mod.strategy, "propose_llm_async", fake_llm)
    out = await graph_mod.propose(_gen1_state("llm"))  # type: ignore[arg-type]
    assert out["_proposer"] == "llm"
    assert out["proposed"] == [("CCO", None)] * 3


async def test_propose_llm_accumulates_cost(monkeypatch) -> None:
    from capychem.proposer import ProposalResult

    async def fake_llm(task, population, *, n, seed):
        return [
            ProposalResult(raw="CCO", smiles="CCO", tokens_in=5, tokens_out=3, cost_usd=0.1)
            for _ in range(n)
        ]

    monkeypatch.setattr(graph_mod.strategy, "propose_llm_async", fake_llm)
    state = _gen1_state("llm")
    state["llm_cost_usd"] = 0.25  # cost carried from a prior generation
    out = await graph_mod.propose(state)  # type: ignore[arg-type]
    # offspring=3 proposals * 0.1 each = 0.3, added to the prior 0.25.
    assert out["llm_cost_usd"] == pytest.approx(0.55)


async def test_propose_graph_ga_does_not_set_llm_cost(monkeypatch) -> None:
    monkeypatch.setattr(
        graph_mod.strategy,
        "ga_fill",
        lambda pop, n, *, mutation_rate, seed: [("CCC", (0, 1))] * n,
    )
    out = await graph_mod.propose(_gen1_state("graph_ga"))  # type: ignore[arg-type]
    assert "llm_cost_usd" not in out
