from __future__ import annotations

import contextlib

import pytest
from capychem.loop import graph as graph_mod


@pytest.mark.asyncio
async def test_propose_opens_gen_span_and_stop_check_ends_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[tuple[int, int]] = []
    ended: list[tuple[int, int]] = []
    monkeypatch.setattr(
        graph_mod.trace,
        "gen_span",
        lambda tid, run_id, gen_index, **md: (opened.append((run_id, gen_index)) or "gen-x"),
    )
    monkeypatch.setattr(
        graph_mod.trace,
        "end_gen_span",
        lambda run_id, gen_index: ended.append((run_id, gen_index)),
    )
    # node spans -> harmless no-op context manager
    monkeypatch.setattr(
        graph_mod.trace, "span", lambda *a, **k: contextlib.nullcontext("node-x")
    )

    state = {
        "run_id": 7,
        "run_trace_id": "trace-1",
        "gen_span_id": None,
        "gen_index": 0,
        "task": "qed",
        "seed": 42,
        "pop_size": 5,
        "budget": 100,
        "calls_used": 0,
        "max_generations": 50,
        "plateau_window": 5,
        "_made_progress": True,
    }
    out = await graph_mod.propose(state)  # gen 0: loads starting pop, opens gen span
    assert opened == [(7, 0)]
    assert out["gen_span_id"] == "gen-x"

    state.update(out)
    await graph_mod.stop_check(state)  # ends the gen span for this generation
    assert ended == [(7, 0)]
