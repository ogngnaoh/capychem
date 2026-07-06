"""Slice 07-08 backend wiring: a completed run's snapshot exposes per-candidate quality
(top-K tiles) + run-level diversity/novelty (novelty threaded from the gen-0 seed).
"""

from __future__ import annotations

import asyncio

import httpx
from capychem.api.main import app
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport


async def test_completed_run_snapshot_exposes_quality_diversity_novelty() -> None:
    # A few generations so novelty (final pop vs the gen-0 seed) is meaningful.
    body = {
        "task": "qed", "budget": 40, "seed": 42, "pop_size": 6, "offspring": 6,
        "max_generations": 4, "mutation_strategy": "graph_ga",
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
            snap = (await c.get(f"/runs/{run_id}")).json()
    assert isinstance(snap["diversity"], float)  # internal diversity surfaced
    assert snap["novelty"] is not None  # threaded from the gen-0 seed_pop
    assert snap["top_k"], "expected top-K molecules"
    assert snap["top_k"][0]["quality"]["valid"] is True  # per-candidate quality badge data
