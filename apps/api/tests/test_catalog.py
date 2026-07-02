"""GET /catalog + the catalog module it's built on: 23 PMO tasks, grouped in
plain language (milestone 05 slice 03a)."""

from __future__ import annotations

import httpx
from capychem.api.catalog import GROUP_ORDER, TASKS, catalog_groups, task_info
from capychem.api.main import app
from capychem.eval.tasks import PMO_TASKS
from httpx_ws.transport import ASGIWebSocketTransport


def test_catalog_covers_all_23_pmo_tasks() -> None:
    assert {t.name for t in TASKS} == set(PMO_TASKS)
    assert len(TASKS) == 23


def test_catalog_groups_match_group_order_and_are_exhaustive() -> None:
    groups = catalog_groups()
    assert [g["group"] for g in groups] == list(GROUP_ORDER)
    total = sum(len(g["tasks"]) for g in groups)
    assert total == 23
    seen = {t["name"] for g in groups for t in g["tasks"]}
    assert seen == set(PMO_TASKS)


def test_task_info_lookup() -> None:
    info = task_info("qed")
    assert info is not None
    assert info.group == "Drug-likeness"
    assert task_info("not_a_real_task") is None


async def test_get_catalog_endpoint_returns_grouped_23() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r = await c.get("/catalog")
            assert r.status_code == 200
            body = r.json()
            assert [g["group"] for g in body] == list(GROUP_ORDER)
            total = sum(len(g["tasks"]) for g in body)
            assert total == 23
            for g in body:
                for t in g["tasks"]:
                    assert set(t.keys()) == {"name", "description"}
