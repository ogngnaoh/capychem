"""REST routes for runs: create, snapshot, stop."""

from __future__ import annotations

from typing import Any

from capychem.api.runner import RunRegistry
from capychem.api.schemas import AnalyzerHypothesisOut, CreateRunRequest, RunSnapshot
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
        top = summary.get("top_k", [])
        return RunSnapshot(
            run_id=row.id,
            task=row.task,
            status=row.status,
            budget=row.budget,
            plateau_window=row.plateau_window,
            generation_index=summary.get("generations", 0),
            oracle_calls_used=summary.get("oracle_calls", 0),
            best_score=(top[0]["score"] if top else None),
            top_k=top,
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
