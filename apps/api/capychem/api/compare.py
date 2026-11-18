"""Pure aggregation for GET /compare (no DB, no app state).

Overlays two runs' sparse AUC curves on one shared oracle-call x-axis and
assembles the compare payload from two RunSnapshots. This resamples the
*display* curve for overlay; it computes no AUC scalar (RunSnapshot lacks the
full scored buffer eval.metric.top_auc needs), so the "AUC only via the eval
module" rule does not apply here.
"""

from __future__ import annotations

from capychem.api.schemas import (
    AucOverlayPoint,
    ComparePayload,
    CompareRun,
    CurvePoint,
    RunSnapshot,
)


def _value_at(curve: list[CurvePoint], x: int) -> float | None:
    """Step-hold lookup: the last top10_mean at oracle_calls <= x. None before
    the run's first scored generation (no top-10 yet). Past the run's last point
    the value is held flat — running-best top-10 mean does not decrease once the
    run stops adding oracle calls."""
    if not curve or x < curve[0].oracle_calls:
        return None
    val = curve[0].top10_mean
    for p in curve:
        if p.oracle_calls > x:
            break
        val = p.top10_mean
    return val


def resample_auc_to_common_axis(
    curve_a: list[CurvePoint], curve_b: list[CurvePoint]
) -> list[AucOverlayPoint]:
    """Resample both curves onto one shared x grid (the sorted union of every
    oracle_calls), so the two series are overlay-comparable."""
    xs = sorted({p.oracle_calls for p in curve_a} | {p.oracle_calls for p in curve_b})
    return [
        AucOverlayPoint(oracle_calls=x, a=_value_at(curve_a, x), b=_value_at(curve_b, x))
        for x in xs
    ]


def _compare_run(s: RunSnapshot) -> CompareRun:
    return CompareRun(
        run_id=s.run_id,
        task=s.task,
        mode=s.mode,
        status=s.status,
        best_score=s.best_score,
        oracle_calls=s.oracle_calls_used,
        budget=s.budget,
        cost_so_far_usd=s.cost_so_far_usd,
        top_k=s.top_k,
        hypotheses=s.hypotheses,
    )


def build_compare_payload(a: RunSnapshot, b: RunSnapshot) -> ComparePayload:
    return ComparePayload(
        a=_compare_run(a),
        b=_compare_run(b),
        auc_overlay=resample_auc_to_common_axis(a.auc_curve, b.auc_curve),
    )
