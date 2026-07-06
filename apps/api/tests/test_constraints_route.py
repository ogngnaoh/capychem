"""Slice 07-04b: hard constraints at the /runs boundary force exploratory, and a
malformed constraints spec (bad SMARTS / unknown catalog) is a 422.
"""

from __future__ import annotations

import httpx
from capychem.api.routes_runs import router
from capychem.run import RunConfig
from fastapi import FastAPI


class _CaptureRegistry:
    def __init__(self) -> None:
        self.cfg: RunConfig | None = None

    async def start_run(self, cfg: RunConfig) -> int:
        self.cfg = cfg
        return 77


def _app() -> tuple[FastAPI, _CaptureRegistry]:
    app = FastAPI()
    app.include_router(router)
    reg = _CaptureRegistry()
    app.state.registry = reg
    return app, reg


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


_BODY = {"task": "qed", "budget": 40, "seed": 42, "pop_size": 20, "offspring": 10}


async def test_constraints_run_is_exploratory() -> None:
    app, reg = _app()
    constraints = {"catalogs": ["PAINS"], "smarts_exclude": ["[N+](=O)[O-]"]}
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "constraints_json": constraints})
        assert r.status_code == 201
    assert reg.cfg is not None
    assert reg.cfg.constraints_json == constraints
    assert reg.cfg.mode == "exploratory"


async def test_invalid_smarts_rejected_at_runs_boundary() -> None:
    app, reg = _app()
    bad = {"smarts_exclude": ["not[smarts"]}
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "constraints_json": bad})
        assert r.status_code == 422
    assert reg.cfg is None


async def test_unknown_catalog_rejected() -> None:
    app, reg = _app()
    async with _client(app) as c:
        r = await c.post("/runs", json={**_BODY, "constraints_json": {"catalogs": ["BOGUS"]}})
        assert r.status_code == 422
    assert reg.cfg is None
