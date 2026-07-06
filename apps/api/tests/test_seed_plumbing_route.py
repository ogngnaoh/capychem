"""Slice 07-02: the /runs boundary validates operator seed SMILES (a client can
POST directly, so this validation is authoritative — not the intent preview) and
a custom seed forces mode=exploratory without touching the integer RNG seed.
"""

from __future__ import annotations

import httpx
from capychem.api.routes_runs import router
from capychem.run import RunConfig
from fastapi import FastAPI


class _CaptureRegistry:
    """Records the RunConfig create_run_endpoint builds, without driving a loop."""

    def __init__(self) -> None:
        self.cfg: RunConfig | None = None

    async def start_run(self, cfg: RunConfig) -> int:
        self.cfg = cfg
        return 123


def _app() -> tuple[FastAPI, _CaptureRegistry]:
    app = FastAPI()
    app.include_router(router)
    reg = _CaptureRegistry()
    app.state.registry = reg
    return app, reg


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


_BODY = {"task": "qed", "budget": 40, "seed": 42, "pop_size": 20, "offspring": 10}


async def test_custom_seed_is_exploratory_custom_and_preserves_rng_seed() -> None:
    app, reg = _app()
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "seed_smiles": ["CCO", "CCN"]})
        assert r.status_code == 201
    assert reg.cfg is not None
    assert reg.cfg.seed_smiles == ["CCO", "CCN"]
    assert reg.cfg.seed_source == "custom"
    assert reg.cfg.mode == "exploratory"
    assert reg.cfg.seed == 42  # the integer RNG seed is untouched (G6)


async def test_no_seed_is_benchmark_default() -> None:
    app, reg = _app()
    async with _client(app) as c:
        r = await c.post("/runs", json=_BODY)
        assert r.status_code == 201
    assert reg.cfg is not None
    assert reg.cfg.seed_smiles is None
    assert reg.cfg.seed_source == "default"
    assert reg.cfg.mode == "benchmark"


async def test_empty_seed_list_stays_benchmark() -> None:
    app, reg = _app()
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "seed_smiles": []})
        assert r.status_code == 201
    assert reg.cfg is not None
    assert reg.cfg.mode == "benchmark"  # [] is "no custom input" (derive_mode)
    assert reg.cfg.seed_source == "default"


async def test_invalid_seed_smiles_rejected_at_boundary() -> None:
    app, reg = _app()
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "seed_smiles": ["CCO", "not-a-smiles"]})
        assert r.status_code == 422
    assert reg.cfg is None  # never reached the registry


async def test_seeded_run_reaches_gen0_population_end_to_end() -> None:
    """Full glue against the real app: a POSTed seed reaches the gen-0 population
    and the run is exploratory. graph_ga + max_generations=1 runs exactly gen 0
    (scores the seed population), so a distinctive seed survives into top_k.

    Uses the shared dev Postgres + harness scoring (slow, ~seconds) — the only
    test proving the route -> runner -> gen-0 threading end to end."""
    import asyncio

    from capychem.api.main import app as real_app
    from httpx_ws import aconnect_ws
    from httpx_ws.transport import ASGIWebSocketTransport

    seed = "c1ccccc1"  # benzene; its RDKit-canonical form is itself
    body = {
        "task": "qed", "budget": 100, "seed": 42, "pop_size": 4, "offspring": 4,
        "max_generations": 1, "mutation_strategy": "graph_ga", "seed_smiles": [seed],
    }
    async with real_app.router.lifespan_context(real_app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(real_app), base_url="http://test"
        ) as c:
            run_id = (await c.post("/runs", json=body)).json()["run_id"]
            async with asyncio.timeout(120):
                async with aconnect_ws(f"http://test/ws/runs/{run_id}", c) as ws:
                    while True:
                        msg = await ws.receive_json()
                        if msg["type"] == "run.complete":
                            break
            snap = (await c.get(f"/runs/{run_id}")).json()
    assert snap["mode"] == "exploratory"  # custom seed dropped it out of benchmark
    assert seed in [m["smiles"] for m in snap["top_k"]]  # operator seed reached gen 0
