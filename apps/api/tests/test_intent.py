"""POST /intent/resolve + the deterministic resolver behind it (FR-015 guardrails,
milestone 05 slice 03a). Deterministic path only — no LLM, no network."""

from __future__ import annotations

import httpx
from capychem.api.intent import DeterministicResolver, resolve_intent
from capychem.api.main import app
from httpx_ws.transport import ASGIWebSocketTransport

# --- pure resolver -----------------------------------------------------------


def test_deterministic_resolver_high_confidence_exact_alias() -> None:
    result = DeterministicResolver().resolve("jnk3 kinase inhibitor")
    assert result.task == "jnk3"
    assert result.confidence == "high"


def test_deterministic_resolver_grounded_to_catalog_only() -> None:
    """Any match, at any confidence, names one of the 23 PMO tasks — never an
    invented oracle."""
    from capychem.eval.tasks import PMO_TASKS

    for text in ["drug-like", "totally unrelated gibberish qwxyz", "similar to albuterol"]:
        result = DeterministicResolver().resolve(text)
        task = result.task or result.closest_task
        assert task in PMO_TASKS


def test_resolve_intent_high_confidence_match_builds_plan() -> None:
    out = resolve_intent("overall drug-likeness, easy to synthesize")
    assert out.matched_task == "qed"
    assert out.confidence in {"high", "medium"}
    assert out.resolved_plan is not None
    assert out.resolved_plan.task == "qed"
    assert out.resolved_plan.budget > 0
    assert out.refusals == []
    assert out.cost_usd == 0.0


def test_resolve_intent_no_confident_match_sets_closest_and_null_plan() -> None:
    out = resolve_intent("please invent a molecule that cures the common cold")
    assert out.matched_task is None
    assert out.closest_task is not None
    assert "closest" in out.rationale.lower() or "no benchmark" in out.rationale.lower()
    assert out.resolved_plan is None


def test_resolve_intent_empty_text_refuses_on_objective_field() -> None:
    out = resolve_intent("   ")
    fields = {r.field for r in out.refusals}
    assert "objective" in fields
    assert out.resolved_plan is None


def test_resolve_intent_invalid_seed_smiles_refuses() -> None:
    out = resolve_intent("jnk3 kinase", seed_smiles="not a smiles!!")
    fields = {r.field for r in out.refusals}
    assert "seed_smiles" in fields
    assert out.resolved_plan is None


def test_resolve_intent_valid_seed_smiles_passes_through() -> None:
    out = resolve_intent("jnk3 kinase", seed_smiles="c1ccccc1")
    assert out.refusals == []
    assert out.resolved_plan is not None
    assert out.resolved_plan.seed_smiles == "c1ccccc1"


def test_resolve_intent_nonpositive_budget_refuses() -> None:
    out = resolve_intent("jnk3 kinase", budget=0)
    fields = {r.field for r in out.refusals}
    assert "budget" in fields
    assert out.resolved_plan is None


def test_resolve_intent_oversized_budget_refuses() -> None:
    out = resolve_intent("jnk3 kinase", budget=10_000_000)
    fields = {r.field for r in out.refusals}
    assert "budget" in fields
    assert out.resolved_plan is None


def test_resolve_intent_default_budget_used_when_omitted() -> None:
    out = resolve_intent("jnk3 kinase")
    assert out.resolved_plan is not None
    assert out.resolved_plan.budget == 10_000


# --- route wiring -------------------------------------------------------------


async def test_post_intent_resolve_route_good_match() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r = await c.post("/intent/resolve", json={"text": "jnk3 kinase activity"})
            assert r.status_code == 200
            body = r.json()
            assert body["matched_task"] == "jnk3"
            assert body["resolved_plan"]["task"] == "jnk3"
            assert body["cost_usd"] == 0.0


async def test_post_intent_resolve_route_no_match() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r = await c.post(
                "/intent/resolve", json={"text": "gibberish that matches nothing zzqx"}
            )
            assert r.status_code == 200
            body = r.json()
            assert body["matched_task"] is None
            assert body["closest_task"] is not None
            assert body["resolved_plan"] is None
