"""Run-row config + lifecycle helpers, shared by the CLI and the API.

Keeps the Run row's create/finalize logic in one place so the CLI driver and the
FastAPI background runner agree on column population and terminal status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from capychem.db.models import Run
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


async def create_run(session: AsyncSession, config: RunConfig) -> int:
    """Insert a Run row (status='running') and return its id."""
    row = Run(
        task=config.task,
        budget=config.budget,
        mutation_strategy="graph_ga",
        plateau_window=config.plateau_window,
        pop_size=config.pop_size,
        offspring=config.offspring,
        mutation_rate=config.mutation_rate,
        seed=config.seed,
        status="running",
    )
    session.add(row)
    await session.commit()
    return row.id


async def finalize_run(session: AsyncSession, run_id: int, final_state: dict[str, Any]) -> None:
    """Set terminal status + summary_json from the loop's final state."""
    row = await session.get(Run, run_id)
    if row is None:  # defensive; the row was just created by us
        return
    row.status = final_state.get("stop_reason") or "exhausted"
    row.summary_json = final_state.get("summary")
    await session.commit()
