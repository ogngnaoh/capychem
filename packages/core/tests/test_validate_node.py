"""The validate node accumulates per-run parse-validity stats across generations.

trace.span() no-ops without LANGFUSE_* keys, so this needs no Langfuse. The node
is async; the test runner runs `async def` tests directly (see conftest).
"""

from __future__ import annotations

from typing import Any

from capychem.loop.graph import validate


async def test_validate_node_accumulates_stats_across_generations() -> None:
    proposed = [("CCO", None), ("OCC", None), ("not_a_smiles", None)]  # 2 valid of 3
    state: dict[str, Any] = {
        "proposed": proposed,
        "run_trace_id": None,
        "gen_span_id": None,
    }
    out1 = await validate(state)  # type: ignore[arg-type]
    assert out1["_validation_stats"] == {"proposed": 3, "valid": 2}
    # validated dedups (OCC == CCO) -> 1 unique, even though both count as valid
    assert len(out1["validated"]) == 1

    # Simulate LangGraph merging the prior stats back into state for gen 2.
    state2: dict[str, Any] = {**state, "_validation_stats": out1["_validation_stats"]}
    out2 = await validate(state2)  # type: ignore[arg-type]
    assert out2["_validation_stats"] == {"proposed": 6, "valid": 4}


async def test_validate_node_tags_candidates_with_proposer() -> None:
    state: dict[str, Any] = {
        "proposed": [("CCO", None), ("c1ccccc1", None)],
        "_proposer": "llm",
        "run_trace_id": None,
        "gen_span_id": None,
    }
    out = await validate(state)  # type: ignore[arg-type]
    assert {c.proposer for c in out["validated"]} == {"llm"}


async def test_validate_node_defaults_proposer_to_graph_ga() -> None:
    state: dict[str, Any] = {
        "proposed": [("CCO", None)],
        "run_trace_id": None,
        "gen_span_id": None,
    }
    out = await validate(state)  # type: ignore[arg-type]
    assert out["validated"][0].proposer == "graph_ga"
