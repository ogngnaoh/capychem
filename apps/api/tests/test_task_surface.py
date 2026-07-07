"""Task-surface validation: jnk3 accepted alongside qed; unknown tasks refused
(FR-015); launch config (task / mutation_strategy / plateau_window) reaches the
persisted Run row. The mapping test disables the inline worker (m08-02) so
POST /runs enqueues without driving a real loop."""

from __future__ import annotations

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
    from capychem.db.models import Run

    # Disable the inline worker (m08-02): this test only checks that the
    # launch config reaches the persisted Run row, not that the loop runs —
    # a "jnk3"/"llm" run would otherwise actually get claimed and driven
    # against real DeepSeek by the background worker.
    monkeypatch.setenv("CAPYCHEM_INLINE_WORKER", "0")
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            body = {"task": "jnk3", "budget": 50, "mutation_strategy": "llm", "plateau_window": 7}
            r = await c.post("/runs", json=body)
            assert r.status_code == 201
            assert r.json()["status"] == "queued"
            run_id = r.json()["run_id"]
            async with app.state.sessionmaker() as session:
                row = await session.get(Run, run_id)
    assert row is not None
    assert row.status == "queued"  # inline worker disabled -> never claimed
    assert row.task == "jnk3"
    assert row.mutation_strategy == "llm"
    assert row.plateau_window == 7


async def test_post_runs_rejects_unknown_task() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r = await c.post("/runs", json={"task": "not_a_real_task", "budget": 10})
            assert r.status_code == 422
