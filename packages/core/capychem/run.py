"""Run-row config + lifecycle helpers, shared by the CLI and the API.

Keeps the Run row's create/finalize logic in one place so the CLI driver and the
FastAPI background runner agree on column population and terminal status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from capychem.db.models import OracleCall, Run
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RunConfig:
    task: str
    budget: int
    seed: int
    pop_size: int
    offspring: int
    mutation_rate: float
    plateau_window: int
    max_generations: int
    mutation_strategy: str = "graph_ga"
    # benchmark|exploratory — server-derived via capychem.mode.derive_mode, never
    # client-set. Only benchmark runs feed the committed G1 numbers (07-01).
    mode: str = "benchmark"
    # Operator bring-your-own starting compounds (07-02, FR-001); None -> default
    # pool. seed_source is default|custom. A non-null seed_smiles forces exploratory
    # (via derive_mode at the route). Distinct from the integer RNG ``seed``.
    seed_smiles: list[str] | None = None
    seed_source: str = "default"
    # Composed exploratory objective spec (07-04); None -> single-task benchmark
    # scoring (byte-identical). A non-null objective forces exploratory via derive_mode.
    objective_json: dict[str, Any] | None = None
    # Hard constraints spec (07-04b); None -> no constraint filtering. A non-null
    # constraints set forces exploratory via derive_mode.
    constraints_json: dict[str, Any] | None = None


async def create_run(session: AsyncSession, config: RunConfig, *, status: str = "running") -> int:
    """Insert a Run row and return its id.

    ``status`` defaults to "running" (the CLI driver and RunRegistry.start_run's
    single-shot self-claim both drive the run themselves immediately, so there
    is no queued interval to represent). The producer path (POST /runs,
    capychem.api.routes_runs.create_run_endpoint) passes status="queued": the
    row sits in the durable queue until a worker's claim_next_run
    (capychem.db.queue) picks it up (milestone 08 slice 02).
    """
    row = Run(
        task=config.task,
        budget=config.budget,
        mutation_strategy=config.mutation_strategy,
        plateau_window=config.plateau_window,
        max_generations=config.max_generations,
        pop_size=config.pop_size,
        offspring=config.offspring,
        mutation_rate=config.mutation_rate,
        seed=config.seed,
        status=status,
        mode=config.mode,
        seed_smiles=config.seed_smiles,
        seed_source=config.seed_source,
        objective_json=config.objective_json,
        constraints_json=config.constraints_json,
    )
    session.add(row)
    await session.commit()
    return row.id


def build_manifest(
    config: RunConfig,
    *,
    git_sha: str | None,
    model_id: str | None,
    pytdc_version: str | None,
    trace_url: str | None,
) -> dict[str, Any]:
    """A citable reproducibility manifest (OD-5): what to pin to rerun this exact run —
    code (git SHA), model (id), oracle (PyTDC version), the full launch config, and the
    Langfuse trace. Any field may be None (best-effort provenance)."""
    return {
        "git_sha": git_sha,
        "model_id": model_id,
        "pytdc_version": pytdc_version,
        "trace_url": trace_url,
        "config": {
            "task": config.task,
            "budget": config.budget,
            "seed": config.seed,
            "pop_size": config.pop_size,
            "offspring": config.offspring,
            "mutation_rate": config.mutation_rate,
            "plateau_window": config.plateau_window,
            "max_generations": config.max_generations,
            "mutation_strategy": config.mutation_strategy,
            "mode": config.mode,
            "seed_source": config.seed_source,
            "objective_json": config.objective_json,
            "constraints_json": config.constraints_json,
        },
    }


async def finalize_run(
    session: AsyncSession,
    run_id: int,
    final_state: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> None:
    """Set terminal status + summary_json from the loop's final state; persist the
    reproducibility manifest (OD-5) and backfill each OracleCall's oracle_version from
    its PyTDC pin in a single UPDATE (cheaper than per-call at score time)."""
    row = await session.get(Run, run_id)
    if row is None:  # defensive; the row was just created by us
        return
    row.status = final_state.get("stop_reason") or "exhausted"
    row.summary_json = final_state.get("summary")
    if manifest is not None:
        row.manifest_json = manifest
        pin = manifest.get("pytdc_version")
        if pin is not None:
            await session.execute(
                update(OracleCall).where(OracleCall.run_id == run_id).values(oracle_version=pin)
            )
    await session.commit()
