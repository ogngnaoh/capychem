"""REST routes for runs: create, snapshot, stop."""

from __future__ import annotations

from typing import Any

from capychem.api.runner import RunRegistry
from capychem.api.schemas import CreateRunRequest, RunSnapshot
from capychem.db.models import Run
from capychem.run import RunConfig
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

router = APIRouter()


def _registry(request: Request) -> RunRegistry:
    reg: RunRegistry = request.app.state.registry
    return reg


def _sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    sm: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
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
    )
    run_id = await _registry(request).start_run(cfg)
    return {"run_id": run_id, "status": "running"}


@router.get("/runs/{run_id}", response_model=RunSnapshot)
async def get_run_endpoint(run_id: int, request: Request) -> RunSnapshot:
    live = _registry(request).snapshot(run_id)
    if live is not None:
        return RunSnapshot(**live)
    # Terminal / not-in-registry (e.g. after a restart): read the DB row.
    # summary_json comes from build_summary: top_k is [{smiles, score}] and
    # auc_curve is [{oracle_calls, top10_mean}] — both match the schema dicts.
    sm = _sessionmaker(request)
    async with sm() as session:
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
            generation_index=summary.get("generations", 0),
            oracle_calls_used=summary.get("oracle_calls", 0),
            best_score=(top[0]["score"] if top else None),
            top_k=top,
            auc_curve=summary.get("auc_curve", []),
        )


@router.post("/runs/{run_id}/stop")
async def stop_run_endpoint(run_id: int, request: Request) -> dict[str, Any]:
    ok = await _registry(request).stop_run(run_id)
    if not ok:
        # Unknown run or already terminal — idempotent no-op if the row exists.
        sm = _sessionmaker(request)
        async with sm() as session:
            row = await session.get(Run, run_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"run_id": run_id, "status": "stopping"}
