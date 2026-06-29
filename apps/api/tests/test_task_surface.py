"""Task-surface validation: jnk3 accepted alongside qed; unknown tasks refused
(FR-015); launch config (task / mutation_strategy / plateau_window) reaches RunConfig.
The mapping test stubs RunRegistry.start_run so no real loop runs."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from capychem.api.main import app
from capychem.api.schemas import CreateRunRequest
from httpx_ws.transport import ASGIWebSocketTransport
from pydantic import ValidationError


def test_schema_accepts_jnk3_and_qed() -> None:
    assert CreateRunRequest(task="jnk3", budget=10).task == "jnk3"
    assert CreateRunRequest(task="qed", budget=10).task == "qed"
    assert CreateRunRequest(budget=10).task == "qed"  # default unchanged


def test_schema_rejects_unknown_task() -> None:
    with pytest.raises(ValidationError):
        CreateRunRequest(task="not_a_real_task", budget=10)


def test_schema_accepts_full_pmo_surface() -> None:
    from capychem.eval.tasks import PMO_TASKS

    for task in PMO_TASKS:
        assert CreateRunRequest(task=task, budget=10).task == task
    # drd2 was the old "unknown" fixture; it is a real PMO task and now valid.
    assert CreateRunRequest(task="drd2", budget=10).task == "drd2"


async def test_post_runs_maps_task_strategy_plateau_to_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from capychem.api import runner as runner_mod

    captured: dict[str, Any] = {}

    async def fake_start(self: Any, cfg: Any) -> int:
        captured["cfg"] = cfg
        return 4242

    monkeypatch.setattr(runner_mod.RunRegistry, "start_run", fake_start)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            body = {"task": "jnk3", "budget": 50, "mutation_strategy": "llm", "plateau_window": 7}
            r = await c.post("/runs", json=body)
            assert r.status_code == 201
            assert r.json()["run_id"] == 4242
    cfg = captured["cfg"]
    assert cfg.task == "jnk3"
    assert cfg.mutation_strategy == "llm"
    assert cfg.plateau_window == 7


async def test_post_runs_rejects_unknown_task() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r = await c.post("/runs", json={"task": "not_a_real_task", "budget": 10})
            assert r.status_code == 422
