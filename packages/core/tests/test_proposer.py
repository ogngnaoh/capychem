"""Env-selected proposer backend + cost mapping (milestone-02 slice 03)."""

from __future__ import annotations

import asyncio

import pytest
from capychem import proposer
from capychem.proposer import (
    ProposalResult,
    ProposerError,
    _clean_smiles,
    propose_batch_async,
)


def test_clean_smiles_strips_fences_and_prose():
    assert _clean_smiles("```\nCCO\n```") == "CCO"
    assert _clean_smiles("  c1ccccc1  ") == "c1ccccc1"
    assert _clean_smiles("CCO and more text") == "CCO"
    assert _clean_smiles("```smiles\nCC(=O)O\n```") == "CC(=O)O"
    assert _clean_smiles("") == ""


async def test_stub_is_deterministic_and_free(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")
    a = await propose_batch_async("make a molecule", 5, seed=42)
    b = await propose_batch_async("make a molecule", 5, seed=42)
    assert [r.smiles for r in a] == [r.smiles for r in b]
    assert len(a) == 5
    assert all(r.cost_usd == 0.0 for r in a)
    assert all(isinstance(r, ProposalResult) for r in a)


async def test_stub_seed_changes_output(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")
    a = await propose_batch_async("p", 8, seed=1)
    b = await propose_batch_async("p", 8, seed=2)
    assert [r.smiles for r in a] != [r.smiles for r in b]


async def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "bogus")
    with pytest.raises(ValueError, match="CAPYCHEM_PROPOSER_BACKEND"):
        await propose_batch_async("p", 1)


async def test_modal_backend_maps_tokens_to_cost(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "modal")
    monkeypatch.setenv("CAPYCHEM_LLM_USD_PER_1K_IN", "0.001")
    monkeypatch.setenv("CAPYCHEM_LLM_USD_PER_1K_OUT", "0.002")

    class FakeRemote:
        async def aio(self, *, prompt, n, temperature, seed, model):
            return [
                {"raw": "```\nCCO\n```", "tokens_in": 1000, "tokens_out": 500} for _ in range(n)
            ]

    class FakeFn:
        remote = FakeRemote()

    monkeypatch.setattr(proposer, "_modal_propose_fn", lambda: FakeFn())
    out = await propose_batch_async("prompt", 2, temperature=0.0, seed=7)
    assert len(out) == 2
    assert out[0].smiles == "CCO"
    assert out[0].raw == "```\nCCO\n```"
    assert out[0].cost_usd == pytest.approx(0.002)


async def test_modal_malformed_row_raises(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "modal")

    class FakeRemote:
        async def aio(self, **kwargs):
            return [{"raw": "CCO"}]

    class FakeFn:
        remote = FakeRemote()

    monkeypatch.setattr(proposer, "_modal_propose_fn", lambda: FakeFn())
    with pytest.raises(ProposerError, match="malformed"):
        await propose_batch_async("p", 1)


async def test_direct_backend_fans_out_one_request_per_proposal(monkeypatch):
    # DeepSeek caps n=1 per request, so n proposals == n single-choice requests,
    # each carrying a per-index seed (seed+i) and its own token usage.
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("CAPYCHEM_LLM_USD_PER_1K_IN", "0.001")
    monkeypatch.setenv("CAPYCHEM_LLM_USD_PER_1K_OUT", "0.002")

    calls = []

    async def fake_chat(payload, *, api_key):
        assert api_key == "sk-test"
        calls.append(payload)
        seed = payload["seed"]
        return {
            "choices": [{"message": {"content": f"CCO{seed}"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

    monkeypatch.setattr(proposer, "_deepseek_chat", fake_chat)
    out = await propose_batch_async("prompt", 3, temperature=0.0, seed=7)

    # one request per proposal, none asking for n>1
    assert len(calls) == 3
    assert all(c.get("n", 1) == 1 for c in calls)
    # per-index seed derivation: seed, seed+1, seed+2
    assert {c["seed"] for c in calls} == {7, 8, 9}
    # results preserve request order and carry per-request usage (not divided)
    assert [r.smiles for r in out] == ["CCO7", "CCO8", "CCO9"]
    assert all(r.tokens_in == 100 and r.tokens_out == 50 for r in out)
    # 100/1000*0.001 + 50/1000*0.002 = 0.0002
    assert out[0].cost_usd == pytest.approx(0.0002)


def test_default_rates_match_configured_model(monkeypatch):
    # The placeholder rates must correspond to the default model. _DEFAULT_MODEL is
    # deepseek-v4-pro ($0.435/$0.87 per M tokens), so the unset-env defaults are
    # 0.000435 / 0.00087 per 1k — NOT the V4-Flash 0.00014 / 0.00028 (which would
    # understate real spend ~3.1x). Not a price guarantee.
    monkeypatch.delenv("CAPYCHEM_LLM_USD_PER_1K_IN", raising=False)
    monkeypatch.delenv("CAPYCHEM_LLM_USD_PER_1K_OUT", raising=False)
    monkeypatch.delenv("CAPYCHEM_LLM_MODEL", raising=False)
    assert proposer.llm_model() == "deepseek-v4-pro"
    assert proposer.llm_usd_per_1k_in() == pytest.approx(0.000435)
    assert proposer.llm_usd_per_1k_out() == pytest.approx(0.00087)


async def test_direct_backend_caps_output_tokens(monkeypatch):
    # _one_proposal_row must send max_tokens to hard-cap the output. Without it a
    # reasoning-mode tail (thousands of tokens) could balloon cost; the cap leaves
    # headroom for long SMILES while bounding the tail.
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    captured: dict = {}

    class FakeResp:
        status_code = 200
        text = "ok"

        def json(self):
            return {
                "choices": [{"message": {"content": "CCO"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

    async def fake_post(payload, *, api_key):
        captured.update(payload)
        return FakeResp()

    monkeypatch.setattr(proposer, "_post_deepseek", fake_post)
    await propose_batch_async("p", 1)
    assert captured["max_tokens"] == 128


async def test_direct_backend_disables_reasoning(monkeypatch):
    # deepseek-v4-pro/flash reason by default: they emit reasoning_content and
    # leave message.content EMPTY until the chain-of-thought finishes (~800 tok).
    # The proposer reads content and wants a short, cheap SMILES, so it must put
    # the model in non-reasoning (chat) mode via thinking={"type":"disabled"}.
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    captured: dict = {}

    class FakeResp:
        status_code = 200
        text = "ok"

        def json(self):
            return {
                "choices": [{"message": {"content": "CCO"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

    async def fake_post(payload, *, api_key):
        captured.update(payload)
        return FakeResp()

    monkeypatch.setattr(proposer, "_post_deepseek", fake_post)
    await propose_batch_async("p", 1)
    assert captured["thinking"] == {"type": "disabled"}


async def test_direct_backend_degrades_transient_failures_to_fallback(monkeypatch):
    # A TRANSIENT per-request failure (timeout, 5xx, 429 rate-limit, or a mid-run
    # 402 once balance runs out) must NOT crash the whole batch: the failed slot
    # degrades to an empty proposal so RDKit rejects it and the loop's Graph-GA
    # fallback fills it (FR-005). Keeps a long unattended run alive on one blip.
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    async def flaky_row(prompt, *, temperature, seed, api_key):
        if seed % 2 == 0:
            raise proposer.TransientProposerError("rate limited")
        return {"raw": f"CCO{seed}", "tokens_in": 10, "tokens_out": 5}

    monkeypatch.setattr(proposer, "_one_proposal_row", flaky_row)
    out = await propose_batch_async("p", 4, seed=0)  # seeds 0,1,2,3 -> 0,2 fail
    assert len(out) == 4
    assert [bool(r.smiles) for r in out] == [False, True, False, True]
    assert out[0].smiles == "" and out[0].cost_usd == 0.0
    assert out[1].smiles == "CCO1"


async def test_direct_backend_config_error_still_propagates(monkeypatch):
    # A non-transient error (e.g. a 400 bad request / bad model) must NOT be
    # silently degraded — that would mask a misconfig as a GA-vs-GA null. It
    # propagates loudly.
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    async def bad_row(prompt, *, temperature, seed, api_key):
        raise ProposerError("DeepSeek API error 400: bad model")

    monkeypatch.setattr(proposer, "_one_proposal_row", bad_row)
    with pytest.raises(ProposerError, match="bad model"):
        await propose_batch_async("p", 4, seed=0)


async def test_deepseek_chat_classifies_transient_status(monkeypatch):
    # 402/429/5xx are transient (degradable); other 4xx are not.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    def resp(code):
        class R:
            status_code = code
            text = f"status {code}"

            def json(self):
                return {}

        return R()

    for code in (402, 429, 500, 503):
        async def fake_post(payload, *, api_key, _c=code):
            return resp(_c)

        monkeypatch.setattr(proposer, "_post_deepseek", fake_post)
        with pytest.raises(proposer.TransientProposerError):
            await proposer._deepseek_chat({}, api_key="sk-test")

    async def fake_post_400(payload, *, api_key):
        return resp(400)

    monkeypatch.setattr(proposer, "_post_deepseek", fake_post_400)
    with pytest.raises(ProposerError) as ei:
        await proposer._deepseek_chat({}, api_key="sk-test")
    assert not isinstance(ei.value, proposer.TransientProposerError)


async def test_direct_backend_http_error_raises_proposer_error(monkeypatch):
    # A 4xx/5xx must surface as a clean ProposerError that includes the API's
    # response body (e.g. DeepSeek's "Invalid n value" message), not a raw httpx error.
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    class FakeResp:
        status_code = 400
        text = '{"error":{"message":"Invalid n value (currently only n = 1 is supported)"}}'

        def json(self):
            raise AssertionError("must not parse body on HTTP error")

    async def fake_post(payload, *, api_key):
        return FakeResp()

    monkeypatch.setattr(proposer, "_post_deepseek", fake_post)
    with pytest.raises(ProposerError, match="Invalid n value"):
        await propose_batch_async("p", 2)


async def test_direct_backend_non_json_body_raises_proposer_error(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    class FakeResp:
        status_code = 200
        text = "<html>gateway timeout</html>"

        def json(self):
            raise ValueError("not json")

    async def fake_post(payload, *, api_key):
        return FakeResp()

    monkeypatch.setattr(proposer, "_post_deepseek", fake_post)
    with pytest.raises(ProposerError, match="non-JSON"):
        await propose_batch_async("p", 1)


async def test_direct_backend_missing_key_raises(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "direct")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ProposerError, match="DEEPSEEK_API_KEY"):
        await propose_batch_async("p", 1)


def test_proposer_concurrency_reads_env(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_CONCURRENCY", "3")
    assert proposer.proposer_concurrency() == 3
    monkeypatch.delenv("CAPYCHEM_PROPOSER_CONCURRENCY", raising=False)
    assert proposer.proposer_concurrency() == 8  # the documented default


async def test_direct_backend_bounds_concurrent_requests(monkeypatch):
    """A large batch must never fan out more than proposer_concurrency() DeepSeek
    requests at once (milestone 08 slice 05 backpressure)."""
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("CAPYCHEM_PROPOSER_CONCURRENCY", "2")

    lock = asyncio.Lock()
    state = {"active": 0, "peak": 0}

    async def slow_row(prompt, *, temperature, seed, api_key):
        async with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.05)
        async with lock:
            state["active"] -= 1
        return {"raw": f"CCO{seed}", "tokens_in": 1, "tokens_out": 1}

    monkeypatch.setattr(proposer, "_one_proposal_row", slow_row)
    out = await propose_batch_async("prompt", 8, seed=0)
    assert len(out) == 8
    assert state["peak"] <= 2
    assert state["peak"] > 0
