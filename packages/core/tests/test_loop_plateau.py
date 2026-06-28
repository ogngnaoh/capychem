"""Node-level test: stop_check stops a run whose top-10 mean has gone flat."""

from __future__ import annotations

import pytest
from capychem.loop.graph import stop_check
from capychem.loop.state import LoopState, Scored


def _state(curve: list[tuple[int, float]], *, plateau_window: int) -> LoopState:
    return {
        "run_id": 1,
        "calls_used": 50,
        "budget": 10_000,
        "gen_index": len(curve) - 1,
        "max_generations": 100,
        "plateau_window": plateau_window,
        "auc_curve": curve,
        "population": [Scored(smiles="CCO", score=0.5, candidate_id=1)],
        "_made_progress": True,
        "run_trace_id": None,
        "gen_span_id": None,
    }


@pytest.mark.asyncio
async def test_stop_check_stops_on_plateau() -> None:
    flat = [(10, 0.4), (20, 0.5), (30, 0.5), (40, 0.5), (50, 0.5)]
    out = await stop_check(_state(flat, plateau_window=3))
    assert out["done"] is True
    assert out["stop_reason"] == "plateaued"
    assert out["summary"] is not None


@pytest.mark.asyncio
async def test_stop_check_continues_while_improving() -> None:
    improving = [(10, 0.1), (20, 0.2), (30, 0.3), (40, 0.4), (50, 0.5)]
    out = await stop_check(_state(improving, plateau_window=3))
    assert out["done"] is False
    assert out["gen_index"] == 5  # gen_index + 1
