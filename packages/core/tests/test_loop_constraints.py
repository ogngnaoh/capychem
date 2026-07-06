"""Slice 07-04b: the score node drops constraint-failing candidates before scoring
(no budget spent), flags a starved generation, and stop_check accumulates the streak.
"""

from __future__ import annotations

from typing import Any

from capychem.loop import graph as graph_mod
from capychem.loop.state import Scored
from capychem.oracle import OracleResult
from capychem.validate import ValidCandidate

_NITRO = "O=[N+]([O-])c1ccccc1"
_EXCLUDE_NITRO = {"smarts_exclude": ["[N+](=O)[O-]"]}


def _fake_sba(score: float, cost: float) -> Any:
    async def sba(smiles: list[str], task: str) -> list[OracleResult]:
        return [
            OracleResult(smiles=s, score=score, valid=True, wall_ms=1, cost_usd=cost)
            for s in smiles
        ]

    return sba


def _score_state(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_id": 1, "gen_index": 1, "task": "qed", "budget": 100,
        "validated": [ValidCandidate("c1ccccc1", None)], "mol_buffer": set(),
        "run_trace_id": None, "gen_span_id": None,
    }
    base.update(over)
    return base


async def test_score_node_drops_constraint_failing_before_scoring(monkeypatch) -> None:
    monkeypatch.setattr(graph_mod, "score_batch_async", _fake_sba(0.5, 0.01))
    out = await graph_mod.score(
        _score_state(
            validated=[ValidCandidate(_NITRO, None), ValidCandidate("c1ccccc1", None)],
            constraints_json=_EXCLUDE_NITRO,
        )
    )  # type: ignore[arg-type]
    scored_smis = [c.smiles for c, *_ in out["_scored"]]
    assert scored_smis == ["c1ccccc1"]  # nitrobenzene dropped, benzene scored
    assert out["_constraint_starved"] is False  # at least one candidate passed


async def test_score_node_flags_starved_generation(monkeypatch) -> None:
    monkeypatch.setattr(graph_mod, "score_batch_async", _fake_sba(0.5, 0.01))
    out = await graph_mod.score(
        _score_state(validated=[ValidCandidate(_NITRO, None)], constraints_json=_EXCLUDE_NITRO)
    )  # type: ignore[arg-type]
    assert out["_scored"] == []  # every candidate failed the constraint
    assert out["_constraint_starved"] is True


def _stop_state(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_id": 1, "gen_index": 2, "budget": 100, "calls_used": 10,
        "max_generations": 100, "plateau_window": 5, "_made_progress": False,
        "population": [Scored("CCO", 0.5)], "auc_curve": [(10, 0.5)],
    }
    base.update(over)
    return base


async def test_stop_check_accumulates_then_resets_starved_streak() -> None:
    out = await graph_mod.stop_check(_stop_state(_constraint_starved=True))  # type: ignore[arg-type]
    assert out["done"] is False
    assert out["constraint_starved_streak"] == 1  # 0 -> 1
    # a starved gen alone must not be read as no_progress
    assert out.get("stop_reason") is None

    # A non-starved generation that made progress continues with the streak reset.
    out2 = await graph_mod.stop_check(
        _stop_state(_constraint_starved=False, constraint_starved_streak=3, _made_progress=True)
    )  # type: ignore[arg-type]
    assert out2["done"] is False
    assert out2["constraint_starved_streak"] == 0  # reset when a gen is not starved
