"""Run cost aggregation + the dollar cost-cap config (slice 4).

oracle_cost_usd is summed from OracleCall.compute_cost_usd; the runner upserts a
RunCost row each generation and trips a clean termination over cost_cap_usd().
LLM cost is summed in from `llm_usd` (milestone 02 slice 05).
"""

from __future__ import annotations

import os

from capychem.db.models import OracleCall, RunCost
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

_DEFAULT_COST_CAP_USD = 50.0  # G2: ~$50/run


def cost_cap_usd() -> float:
    return float(os.environ.get("CAPYCHEM_COST_CAP_USD", _DEFAULT_COST_CAP_USD))


async def oracle_cost_so_far(session: AsyncSession, run_id: int) -> float:
    total = await session.scalar(
        select(func.coalesce(func.sum(OracleCall.compute_cost_usd), 0.0)).where(
            OracleCall.run_id == run_id
        )
    )
    return float(total or 0.0)


async def record_oracle_cost(
    session: AsyncSession, run_id: int, oracle_usd: float, *, llm_usd: float = 0.0
) -> RunCost:
    """Upsert the run's RunCost row with the latest oracle + llm costs.

    ``total_usd`` sums both so the ~$50 cost gate fires on LLM spend too
    (milestone 02 slice 05). ``llm_usd`` defaults to 0.0 so existing oracle-only
    callers (and the graph_ga path, where LLM cost is 0) are unchanged."""
    row = await session.scalar(select(RunCost).where(RunCost.run_id == run_id))
    if row is None:
        row = RunCost(run_id=run_id)
        session.add(row)
    row.oracle_cost_usd = oracle_usd
    row.llm_cost_usd = llm_usd
    row.total_usd = oracle_usd + llm_usd
    await session.commit()
    return row
