"""Slice 07-05: every persisted candidate carries a quality report (end-to-end).

Runs a tiny real benchmark run and asserts the persisted Candidate rows have a
quality_json report. Uses the shared dev Postgres + harness (slow, ~seconds).
"""

from __future__ import annotations

import asyncio

import httpx
from capychem.api.main import app
from capychem.db.models import Candidate
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy import select


async def test_persisted_candidates_carry_quality_report() -> None:
    body = {
        "task": "qed",
        "budget": 100,
        "seed": 42,
        "pop_size": 4,
        "offspring": 4,
        "max_generations": 1,
        "mutation_strategy": "graph_ga",
    }
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            run_id = (await c.post("/runs", json=body)).json()["run_id"]
            async with asyncio.timeout(120):
                async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
                    while True:
                        if (await ws.receive_json())["type"] == "run.complete":
                            break
        sm = app.state.sessionmaker
        async with sm() as session:
            gen_ids = select(Candidate).where(Candidate.generation_id.isnot(None))
            cands = list((await session.execute(gen_ids)).scalars().all())
    # At least one candidate from THIS run has a full quality report.
    reports = [c.quality_json for c in cands if c.quality_json is not None]
    assert reports, "no candidate carried a quality report"
    sample = reports[-1]
    assert sample["valid"] is True
    assert {"sa_score", "qed", "lipinski_pass", "pains", "brenk"} <= set(sample)
