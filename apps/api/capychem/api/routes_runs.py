"""REST routes for runs: create, snapshot, stop."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capychem import cost
from capychem.api import config
from capychem.api.compare import build_compare_payload
from capychem.api.ga_baseline import graph_ga_baseline
from capychem.api.runner import RunRegistry
from capychem.api.schemas import (
    AnalyzerHypothesisOut,
    ComparePayload,
    CreateRunRequest,
    RunListItem,
    RunSnapshot,
)
from capychem.db.models import AnalyzerHypothesis, Run, RunCost
from capychem.mode import derive_mode
from capychem.run import RunConfig
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import HTTPConnection

router = APIRouter()


def _gated_baseline(mode: str, task: str) -> float | None:
    """The G1-contamination gate: a Graph-GA baseline is presentable ONLY for a
    benchmark run. An exploratory run (custom seed/oracle/objective/constraint) has
    no comparable Graph-GA control, so its snapshot never carries one — the single
    rule both the live and DB snapshot paths apply."""
    return graph_ga_baseline(task) if mode == "benchmark" else None


def registry_of(conn: HTTPConnection) -> RunRegistry:
    """App-state accessor shared by the REST routes and the WS endpoint
    (HTTPConnection covers both Request and WebSocket)."""
    reg: RunRegistry = conn.app.state.registry
    return reg


def sessionmaker_of(conn: HTTPConnection) -> async_sessionmaker[AsyncSession]:
    sm: async_sessionmaker[AsyncSession] = conn.app.state.sessionmaker
    return sm


def _db_fields(row: Run) -> tuple[str, float | None, int]:
    """Derive (status, best_score, oracle_calls) for a DB-only run from its
    persisted row + summary_json. The single derivation the list and the
    run-detail endpoint share (the list == detail invariant)."""
    summary = row.summary_json or {}
    top = summary.get("top_k", [])
    best_score = top[0]["score"] if top else None
    return row.status, best_score, summary.get("oracle_calls", 0)


def run_list_item(row: Run, live: dict[str, Any] | None) -> RunListItem:
    """One list row: identity fields always come from the DB row (the live
    snapshot has no started_at); status/best_score/oracle_calls come from the
    registry snapshot when the run is live, else from summary_json."""
    if live is not None:
        status = live["status"]
        best_score = live["best_score"]
        oracle_calls = live["oracle_calls_used"]
    else:
        status, best_score, oracle_calls = _db_fields(row)
    return RunListItem(
        run_id=row.id,
        task=row.task,
        mutation_strategy=row.mutation_strategy,
        mode=row.mode,
        status=status,
        best_score=best_score,
        oracle_calls=oracle_calls,
        budget=row.budget,
        started_at=row.started_at,
    )


_SORT_KEYS = ("started_at", "best_score", "oracle_calls", "status")


def build_run_list(
    rows: list[Run],
    live_by_id: Mapping[int, dict[str, Any] | None],
    *,
    status: str | None,
    task: str | None,
    sort: str,
    order: str,
) -> list[RunListItem]:
    """Merge each row with its live overlay, filter, then sort — all in Python,
    because a live run's best_score/oracle_calls come from the registry, not the
    DB, so a SQL ORDER BY would mis-order live runs."""
    items = [run_list_item(r, live_by_id.get(r.id)) for r in rows]
    if status is not None:
        items = [i for i in items if i.status == status]
    if task is not None:
        items = [i for i in items if i.task == task]

    reverse = order != "asc"
    if sort == "best_score":  # nulls always last, regardless of order
        present = sorted(
            (i for i in items if i.best_score is not None),
            key=lambda i: i.best_score,  # type: ignore[arg-type,return-value]
            reverse=reverse,
        )
        absent = [i for i in items if i.best_score is None]
        return present + absent
    if sort == "oracle_calls":
        return sorted(items, key=lambda i: i.oracle_calls, reverse=reverse)
    if sort == "status":
        return sorted(items, key=lambda i: i.status, reverse=reverse)
    return sorted(items, key=lambda i: i.started_at, reverse=reverse)


@router.post("/runs", status_code=201)
async def create_run_endpoint(body: CreateRunRequest, request: Request) -> dict[str, Any]:
    cfg = RunConfig(
        task=body.task,
        budget=body.budget,
        seed=body.seed,
        pop_size=body.pop_size,
        offspring=body.offspring,
        mutation_rate=body.mutation_rate,
        plateau_window=body.plateau_window,
        max_generations=body.max_generations,
        mutation_strategy=body.mutation_strategy,
        # Operator bring-your-own compounds (07-02). The schema validator already
        # RDKit-checked them and collapsed an empty list to None.
        seed_smiles=body.seed_smiles,
        seed_source="custom" if body.seed_smiles else "default",
        # Server-derived, never client-set: a custom seed (07-02) — or later a custom
        # objective/constraints — forces exploratory; a plain run stays benchmark.
        mode=derive_mode(seed_smiles=body.seed_smiles),
    )
    run_id = await registry_of(request).start_run(cfg)
    return {"run_id": run_id, "status": "running"}


@router.get("/runs", response_model=list[RunListItem])
async def list_runs_endpoint(
    request: Request,
    status: str | None = None,
    task: str | None = None,
    sort: str = "started_at",
    order: str = "desc",
) -> list[RunListItem]:
    if sort not in _SORT_KEYS:
        raise HTTPException(status_code=422, detail=f"sort must be one of {_SORT_KEYS}")
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="order must be 'asc' or 'desc'")
    sm = sessionmaker_of(request)
    registry = registry_of(request)
    async with sm() as session:
        rows = list((await session.execute(select(Run))).scalars().all())
    live_by_id = {row.id: registry.snapshot(row.id) for row in rows}
    return build_run_list(rows, live_by_id, status=status, task=task, sort=sort, order=order)


async def _hypotheses_for(session: AsyncSession, run_id: int) -> list[AnalyzerHypothesisOut]:
    rows = (
        (
            await session.execute(
                select(AnalyzerHypothesis)
                .where(AnalyzerHypothesis.run_id == run_id)
                .order_by(AnalyzerHypothesis.after_generation_index)
            )
        )
        .scalars()
        .all()
    )
    return [
        AnalyzerHypothesisOut(
            after_generation_index=r.after_generation_index,
            text=r.text,
            structured_json=r.structured_json,
        )
        for r in rows
    ]


async def _run_cost_breakdown(
    session: AsyncSession, run_id: int
) -> tuple[float | None, float | None]:
    """(llm_cost_usd, oracle_cost_usd) from the run's RunCost row, or (None, None)
    if it has none yet — the read counterpart to cost.record_oracle_cost, kept
    local to the API layer (packages/core.cost only exposes the summed total)."""
    row = await session.scalar(select(RunCost).where(RunCost.run_id == run_id))
    if row is None:
        return None, None
    return row.llm_cost_usd, row.oracle_cost_usd


async def _run_snapshot(
    session: AsyncSession, registry: RunRegistry, run_id: int
) -> RunSnapshot | None:
    """Build a run's snapshot the single way detail and compare share: the live
    registry snapshot when present, else the persisted DB row (None if unknown —
    the 404 source for both endpoints).

    The DB path covers runs not in the registry (e.g. after a restart) AND a live
    run before its first generation boundary (snapshot stays None until the first
    generation.complete). summary_json comes from build_summary: top_k is
    [{smiles, score}] and auc_curve is [{oracle_calls, top10_mean}] — both match
    the schema dicts. It reads RunCost so completed runs surface real cost
    (FR-013), not the 0.0 default; the live snapshot already carries cost.

    graph_ga_baseline and the llm/oracle cost breakdown are read the same way for
    both the live and DB paths (they don't come from the in-memory snapshot dict);
    valid_smiles_rate only ever comes from a persisted summary_json, so it stays
    null on the live path (matches RunSnapshot's default)."""
    hyps = await _hypotheses_for(session, run_id)
    llm_cost_usd, oracle_cost_usd = await _run_cost_breakdown(session, run_id)
    live = registry.snapshot(run_id)
    if live is not None:
        return RunSnapshot(
            **live,
            hypotheses=hyps,
            # G1-contamination guard (07-01): an exploratory run never presents a
            # Graph-GA baseline, so its snapshot can never render a "beat". mode is
            # carried in the live dict (**live) itself.
            graph_ga_baseline=_gated_baseline(live["mode"], live["task"]),
            llm_cost_usd=llm_cost_usd,
            oracle_cost_usd=oracle_cost_usd,
        )
    row = await session.get(Run, run_id)
    if row is None:
        return None
    summary = row.summary_json or {}
    status, best_score, oracle_calls = _db_fields(row)  # shared with the list view
    return RunSnapshot(
        run_id=row.id,
        task=row.task,
        mode=row.mode,
        status=status,
        budget=row.budget,
        plateau_window=row.plateau_window,
        generation_index=summary.get("generations", 0),
        oracle_calls_used=oracle_calls,
        best_score=best_score,
        top_k=summary.get("top_k", []),
        auc_curve=summary.get("auc_curve", []),
        cost_so_far_usd=await cost.run_cost_total(session, run_id),
        hypotheses=hyps,
        trace_url=config.trace_url(summary.get("trace_id")),
        valid_smiles_rate=(summary.get("valid_smiles") or {}).get("rate"),
        graph_ga_baseline=_gated_baseline(row.mode, row.task),
        llm_cost_usd=llm_cost_usd,
        oracle_cost_usd=oracle_cost_usd,
    )


@router.get("/runs/{run_id}", response_model=RunSnapshot)
async def get_run_endpoint(run_id: int, request: Request) -> RunSnapshot:
    sm = sessionmaker_of(request)
    registry = registry_of(request)
    async with sm() as session:
        snap = await _run_snapshot(session, registry, run_id)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return snap


@router.get("/trace/{run_id}")
async def get_trace_endpoint(run_id: int, request: Request) -> dict[str, str | None]:
    """Langfuse deep link for a run (FR-014 / SPEC §6.3). 404 if the run is
    unknown; ``trace_url`` is null when the run has no persisted trace id or
    LANGFUSE_PROJECT_ID is unconfigured (the UI hides the link, never shows a
    broken one)."""
    sm = sessionmaker_of(request)
    async with sm() as session:
        row = await session.get(Run, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    summary = row.summary_json or {}
    return {"trace_url": config.trace_url(summary.get("trace_id"))}


@router.get("/compare", response_model=ComparePayload)
async def compare_runs_endpoint(request: Request, a: int, b: int) -> ComparePayload:
    """Read-only aggregation of two existing runs (FR-012/013). 404 if either is
    unknown. The two AUC curves are resampled onto a common oracle-call x-axis so
    they overlay-compare (SPEC §6.4d)."""
    sm = sessionmaker_of(request)
    registry = registry_of(request)
    async with sm() as session:
        snap_a = await _run_snapshot(session, registry, a)
        snap_b = await _run_snapshot(session, registry, b)
    if snap_a is None:
        raise HTTPException(status_code=404, detail=f"Run {a} not found")
    if snap_b is None:
        raise HTTPException(status_code=404, detail=f"Run {b} not found")
    return build_compare_payload(snap_a, snap_b)


@router.post("/runs/{run_id}/resume")
async def resume_run_endpoint(run_id: int, request: Request) -> dict[str, Any]:
    """Continue a paused run from its persisted progress (06-07). 404 if the run
    is unknown, 409 if it isn't paused (nothing to resume — the caller should
    check status first, e.g. via GET /runs/{id})."""
    sm = sessionmaker_of(request)
    async with sm() as session:
        row = await session.get(Run, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if row.status != "paused":
        raise HTTPException(
            status_code=409, detail=f"Run {run_id} is not paused (status={row.status!r})"
        )
    try:
        status = await registry_of(request).resume_run(run_id)
    except ValueError as exc:
        # A concurrent resume already claimed this run (TOCTOU past the check above),
        # or its status changed. Refuse rather than spawn a second driver.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # `status` is "running" for a normal resume, or a terminal reason when the run
    # had already finished before it was interrupted (finalized without driving).
    return {"run_id": run_id, "status": status}


@router.post("/runs/{run_id}/stop")
async def stop_run_endpoint(run_id: int, request: Request) -> dict[str, Any]:
    ok = await registry_of(request).stop_run(run_id)
    if not ok:
        # Unknown run or already terminal — idempotent no-op if the row exists;
        # report the row's real status rather than claiming "stopping".
        sm = sessionmaker_of(request)
        async with sm() as session:
            row = await session.get(Run, run_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            return {"run_id": run_id, "status": row.status}
    return {"run_id": run_id, "status": "stopping"}
