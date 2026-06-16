from __future__ import annotations

from capychem.loop.logic import (
    build_summary,
    merge_and_truncate,
    stop_reason,
    trim_to_budget,
)
from capychem.loop.state import Scored


def s(smiles: str, score: float, cid: int | None = None) -> Scored:
    return Scored(smiles=smiles, score=score, candidate_id=cid)


def test_trim_to_budget_caps_batch_to_remaining() -> None:
    items = ["a", "b", "c", "d"]
    assert trim_to_budget(items, budget=10, calls_used=8) == ["a", "b"]
    assert trim_to_budget(items, budget=10, calls_used=10) == []
    assert trim_to_budget(items, budget=10, calls_used=2) == items


def test_merge_and_truncate_keeps_top_pop_size_with_canonical_tiebreak() -> None:
    pop = [s("CCO", 0.5, 1), s("CCN", 0.5, 2)]
    batch = [s("c1ccccc1", 0.9, 3), s("CCC", 0.5, 4)]
    out = merge_and_truncate(pop, batch, pop_size=2)
    assert [m.smiles for m in out] == ["c1ccccc1", "CCC"]  # 0.9 first; ties broken by smiles


def test_stop_reason_budget_exhausted() -> None:
    assert (
        stop_reason(
            calls_used=100, budget=100, gen_index=2, max_generations=100, made_progress=True
        )
        == "exhausted"
    )


def test_stop_reason_max_generations() -> None:
    assert (
        stop_reason(
            calls_used=10, budget=100, gen_index=100, max_generations=100, made_progress=True
        )
        == "max_generations"
    )


def test_stop_reason_zero_progress() -> None:
    assert (
        stop_reason(
            calls_used=10, budget=100, gen_index=3, max_generations=100, made_progress=False
        )
        == "no_progress"
    )


def test_stop_reason_continue() -> None:
    assert (
        stop_reason(calls_used=10, budget=100, gen_index=3, max_generations=100, made_progress=True)
        is None
    )


def test_build_summary_shape() -> None:
    pop = [s("c1ccccc1", 0.9, 3), s("CCO", 0.5, 1)]
    curve = [(20, 0.5), (30, 0.7)]
    summary = build_summary(pop, curve, generations=3, oracle_calls=30, top_k=10)
    assert summary["top_k"][0] == {"smiles": "c1ccccc1", "score": 0.9}
    assert summary["auc_curve"] == [
        {"oracle_calls": 20, "top10_mean": 0.5},
        {"oracle_calls": 30, "top10_mean": 0.7},
    ]
    assert summary["generations"] == 3 and summary["oracle_calls"] == 30


def test_build_summary_includes_valid_smiles_when_stats_given() -> None:
    pop = [s("c1ccccc1", 0.9, 3)]
    summary = build_summary(
        pop,
        [(10, 0.9)],
        generations=1,
        oracle_calls=10,
        validation_stats={"proposed": 40, "valid": 38},
    )
    assert summary["valid_smiles"] == {"proposed": 40, "valid": 38, "rate": 38 / 40}


def test_build_summary_valid_smiles_rate_zero_when_no_proposals() -> None:
    pop = [s("c1ccccc1", 0.9, 3)]
    summary = build_summary(
        pop,
        [(10, 0.9)],
        generations=1,
        oracle_calls=10,
        validation_stats={"proposed": 0, "valid": 0},
    )
    assert summary["valid_smiles"] == {"proposed": 0, "valid": 0, "rate": 0.0}


def test_build_summary_omits_valid_smiles_when_stats_absent() -> None:
    pop = [s("c1ccccc1", 0.9, 3)]
    summary = build_summary(pop, [(10, 0.9)], generations=1, oracle_calls=10)
    assert "valid_smiles" not in summary
