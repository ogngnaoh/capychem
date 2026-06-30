"""Unit tests for the GET /compare aggregation.

Pure (no DB, no app state): `resample_auc_to_common_axis` overlays two sparse
AUC curves on one shared oracle-call x grid, and `build_compare_payload`
assembles two RunSnapshots into the compare payload. `_run_snapshot` (the helper
the detail and compare endpoints share) is exercised against in-memory sqlite to
prove a completed run surfaces RunCost.total_usd and an unknown id returns None.
"""

from __future__ import annotations

from capychem.api.compare import build_compare_payload, resample_auc_to_common_axis
from capychem.api.schemas import (
    AnalyzerHypothesisOut,
    CurvePoint,
    RunSnapshot,
    TopMolecule,
)


def _triples(overlay: list) -> list[tuple[int, float | None, float | None]]:
    return [(p.oracle_calls, p.a, p.b) for p in overlay]


# --- resample_auc_to_common_axis ---------------------------------------------


def test_resample_offset_lengths_carry_forward_and_null_before_start() -> None:
    curve_a = [
        CurvePoint(oracle_calls=32, top10_mean=0.40),
        CurvePoint(oracle_calls=64, top10_mean=0.55),
        CurvePoint(oracle_calls=96, top10_mean=0.60),
    ]
    curve_b = [
        CurvePoint(oracle_calls=50, top10_mean=0.30),
        CurvePoint(oracle_calls=100, top10_mean=0.45),
        CurvePoint(oracle_calls=150, top10_mean=0.50),
    ]
    out = resample_auc_to_common_axis(curve_a, curve_b)
    assert _triples(out) == [
        (32, 0.40, None),  # b not started yet -> null
        (50, 0.40, 0.30),  # a carried forward from 32; b starts
        (64, 0.55, 0.30),  # b carried forward from 50
        (96, 0.60, 0.30),
        (100, 0.60, 0.45),  # a carried forward past its last point (96)
        (150, 0.60, 0.50),  # endpoints align: union max present, a held flat
    ]


def test_resample_endpoints_are_the_union_min_and_max() -> None:
    out = resample_auc_to_common_axis(
        [CurvePoint(oracle_calls=10, top10_mean=0.1)],
        [CurvePoint(oracle_calls=99, top10_mean=0.9)],
    )
    assert out[0].oracle_calls == 10 and out[-1].oracle_calls == 99


def test_resample_empty_b_is_all_null() -> None:
    out = resample_auc_to_common_axis(
        [CurvePoint(oracle_calls=10, top10_mean=0.5), CurvePoint(oracle_calls=20, top10_mean=0.7)],
        [],
    )
    assert _triples(out) == [(10, 0.5, None), (20, 0.7, None)]


def test_resample_both_empty_is_empty() -> None:
    assert resample_auc_to_common_axis([], []) == []


def test_resample_single_points_offset() -> None:
    out = resample_auc_to_common_axis(
        [CurvePoint(oracle_calls=40, top10_mean=0.6)],
        [CurvePoint(oracle_calls=80, top10_mean=0.9)],
    )
    assert _triples(out) == [(40, 0.6, None), (80, 0.6, 0.9)]


# --- build_compare_payload ---------------------------------------------------


def _snap(
    run_id: int,
    *,
    task: str,
    status: str,
    calls: int,
    best: float | None,
    cost: float,
    smiles: str,
    curve: list[CurvePoint],
    hyps: list[AnalyzerHypothesisOut],
) -> RunSnapshot:
    return RunSnapshot(
        run_id=run_id,
        task=task,
        status=status,
        budget=10000,
        plateau_window=5,
        generation_index=len(curve),
        oracle_calls_used=calls,
        best_score=best,
        top_k=[TopMolecule(smiles=smiles, score=best or 0.0)],
        auc_curve=curve,
        cost_so_far_usd=cost,
        hypotheses=hyps,
    )


def test_build_compare_payload_maps_per_run_fields_and_overlay() -> None:
    hyp = AnalyzerHypothesisOut(after_generation_index=1, text="focus amide", structured_json=None)
    a = _snap(
        11,
        task="jnk3",
        status="exhausted",
        calls=10000,
        best=0.88,
        cost=1.23,
        smiles="CCO",
        curve=[
            CurvePoint(oracle_calls=32, top10_mean=0.5),
            CurvePoint(oracle_calls=64, top10_mean=0.7),
        ],
        hyps=[hyp],
    )
    b = _snap(
        9,
        task="qed",
        status="plateaued",
        calls=3400,
        best=0.93,
        cost=0.0,
        smiles="c1ccccc1",
        curve=[CurvePoint(oracle_calls=50, top10_mean=0.4)],
        hyps=[],
    )
    payload = build_compare_payload(a, b)

    assert (payload.a.run_id, payload.a.task, payload.a.status) == (11, "jnk3", "exhausted")
    assert (payload.a.oracle_calls, payload.a.best_score) == (10000, 0.88)
    assert (payload.a.budget, payload.a.cost_so_far_usd) == (10000, 1.23)
    assert payload.a.top_k == a.top_k
    assert payload.a.hypotheses == [hyp]
    assert (payload.b.run_id, payload.b.cost_so_far_usd, payload.b.hypotheses) == (9, 0.0, [])
    # overlay is the resampled union of both curves
    assert payload.auc_overlay == resample_auc_to_common_axis(a.auc_curve, b.auc_curve)
    # x=50: a's last point <=50 is at 32 (0.5), carried forward; b starts at 50 (0.4)
    assert _triples(payload.auc_overlay) == [(32, 0.5, None), (50, 0.5, 0.4), (64, 0.7, 0.4)]


# --- _run_snapshot: cost surfaced for a DB-only completed run, 404 source -----


async def test_run_snapshot_surfaces_runcost_and_none_for_unknown() -> None:
    """The shared snapshot helper reads RunCost.total_usd on the DB path so a
    completed run shows real cost (FR-013), not the 0.0 default; an unknown id
    returns None (the 404 source for both detail and compare)."""
    from capychem.api.routes_runs import _run_snapshot
    from capychem.api.runner import RunRegistry
    from capychem.db.models import Base, Run, RunCost
    from capychem.run import RunConfig, create_run
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    registry = RunRegistry(sm)  # empty -> snapshot() returns None -> DB path

    async with sm() as s:
        run_id = await create_run(
            s,
            RunConfig(
                task="jnk3",
                budget=10000,
                seed=42,
                pop_size=10,
                offspring=4,
                mutation_rate=0.01,
                plateau_window=5,
                max_generations=10,
                mutation_strategy="llm",
            ),
        )
    async with sm() as s:
        row = await s.get(Run, run_id)
        assert row is not None
        row.status = "exhausted"
        row.summary_json = {
            "top_k": [{"smiles": "CCO", "score": 0.88}],
            "oracle_calls": 100,
            "generations": 3,
            "auc_curve": [{"oracle_calls": 32, "top10_mean": 0.5}],
        }
        s.add(RunCost(run_id=run_id, oracle_cost_usd=0.0, llm_cost_usd=2.50, total_usd=2.50))
        await s.commit()

    async with sm() as s:
        snap = await _run_snapshot(s, registry, run_id)
    assert snap is not None
    assert snap.cost_so_far_usd == 2.50  # from RunCost, not the 0.0 default
    assert snap.best_score == 0.88 and snap.oracle_calls_used == 100
    assert snap.status == "exhausted"

    async with sm() as s:
        assert await _run_snapshot(s, registry, 999999) is None
    await engine.dispose()
