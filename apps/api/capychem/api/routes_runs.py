"""REST routes for runs: create, snapshot, stop."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capychem.api.runner import RunRegistry
from capychem.api.schemas import (
    AnalyzerHypothesisOut,
    CreateRunRequest,
    RunListItem,
    RunSnapshot,
)
from capychem.db.models import AnalyzerHypothesis, Run
from capychem.run import RunConfig
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import HTTPConnection

router = APIRouter()


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


async def _hypotheses_for(
    session: AsyncSession, run_id: int
) -> list[AnalyzerHypothesisOut]:
    rows = (
        await session.execute(
            select(AnalyzerHypothesis)
            .where(AnalyzerHypothesis.run_id == run_id)
            .order_by(AnalyzerHypothesis.after_generation_index)
        )
    ).scalars().all()
    return [
        AnalyzerHypothesisOut(
            after_generation_index=r.after_generation_index,
            text=r.text,
            structured_json=r.structured_json,
        )
        for r in rows
    ]


@router.get("/runs/{run_id}", response_model=RunSnapshot)
async def get_run_endpoint(run_id: int, request: Request) -> RunSnapshot:
    sm = sessionmaker_of(request)
    async with sm() as session:
        hyps = await _hypotheses_for(session, run_id)
        live = registry_of(request).snapshot(run_id)
        if live is not None:
            return RunSnapshot(**live, hypotheses=hyps)
        # No in-memory snapshot: read the DB row. Covers runs not in the registry
        # (e.g. after a restart) AND a live run before its first generation boundary
        # (snapshot stays None until the first generation.complete).
        # summary_json comes from build_summary: top_k is [{smiles, score}] and
        # auc_curve is [{oracle_calls, top10_mean}] — both match the schema dicts.
        row = await session.get(Run, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        summary = row.summary_json or {}
        status, best_score, oracle_calls = _db_fields(row)  # shared with the list view
        return RunSnapshot(
            run_id=row.id,
            task=row.task,
            status=status,
            budget=row.budget,
            plateau_window=row.plateau_window,
            generation_index=summary.get("generations", 0),
            oracle_calls_used=oracle_calls,
            best_score=best_score,
            top_k=summary.get("top_k", []),
            auc_curve=summary.get("auc_curve", []),
            hypotheses=hyps,
        )


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
