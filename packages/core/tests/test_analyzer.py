"""Analyzer adapter: stub determinism + hypothesis parsing (milestone-03 slice 01)."""

from __future__ import annotations

import pytest
from capychem import analyzer
from capychem.analyzer import AnalyzerResult, analyze_async, parse_hypothesis


def test_parse_hypothesis_valid() -> None:
    out = parse_hypothesis('Some prose.\n{"focus": "increase logP", "avoid": ["phenol", "nitro"]}')
    assert out == {"focus": "increase logP", "avoid": ["phenol", "nitro"]}


def test_parse_hypothesis_takes_last_block() -> None:
    out = parse_hypothesis('{"focus": "a", "avoid": []} then {"focus": "b", "avoid": ["c"]}')
    assert out == {"focus": "b", "avoid": ["c"]}


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no json here",
        '{"focus": "x"}',  # missing avoid
        '{"avoid": ["y"]}',  # missing focus
        '{"focus": 1, "avoid": ["y"]}',  # focus not a string
        '{"focus": "x", "avoid": "y"}',  # avoid not a list
        '{"focus": "x", "avoid": [1, 2]}',  # avoid items not strings
        "{not valid json}",
    ],
)
def test_parse_hypothesis_rejects_malformed(text: str) -> None:
    assert parse_hypothesis(text) is None


async def test_stub_is_deterministic_and_structured(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    a = await analyze_async("summarize gen 3", seed=7)
    b = await analyze_async("summarize gen 3", seed=7)
    assert isinstance(a, AnalyzerResult)
    assert a.structured == b.structured
    assert a.structured is not None
    assert isinstance(a.structured["focus"], str)
    assert isinstance(a.structured["avoid"], list)
    assert a.cost_usd == 0.0
    assert a.note is None


async def test_stub_seed_varies_hypothesis(monkeypatch) -> None:
    # The stub maps one (seed, prompt) to one of a small pool, so any TWO specific
    # seeds may collide. Assert the stub is seed-SENSITIVE across a range instead.
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    foci = {(await analyze_async("p", seed=s)).structured["focus"] for s in range(10)}
    assert len(foci) > 1


async def test_unknown_backend_raises(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "bogus")
    with pytest.raises(ValueError, match="CAPYCHEM_ANALYZER_BACKEND"):
        await analyze_async("p")


async def test_modal_backend_not_implemented_this_slice(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "modal")
    with pytest.raises(analyzer.ProposerError, match="not implemented"):
        await analyze_async("p")


async def test_direct_payload_disables_reasoning(monkeypatch) -> None:
    # The analyzer now mirrors the proposer: reasoning OFF (thinking:{type:disabled})
    # because v4's CoT overran max_tokens and left message.content empty (parse-rate
    # 0/3 in a real dry run). With reasoning OFF the model emits prose + the
    # {focus,avoid} JSON directly in content (~300 tok), parsing reliably.
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("CAPYCHEM_LLM_USD_PER_1K_IN", "0.001")
    monkeypatch.setenv("CAPYCHEM_LLM_USD_PER_1K_OUT", "0.002")
    captured: dict = {}

    async def fake_chat(payload, *, api_key):
        captured.update(payload)
        assert api_key == "sk-test"
        return {
            "choices": [{"message": {"content": 'ok\n{"focus": "logP", "avoid": ["phenol"]}'}}],
            "usage": {"prompt_tokens": 300, "completion_tokens": 700},
        }

    monkeypatch.setattr(analyzer, "_deepseek_chat", fake_chat)
    out = await analyze_async("analyze this", seed=5)
    assert captured["thinking"] == {"type": "disabled"}  # reasoning OFF
    assert captured["max_tokens"] == analyzer._ANALYZER_MAX_OUTPUT_TOKENS
    assert captured["seed"] == 5
    assert out.structured == {"focus": "logP", "avoid": ["phenol"]}
    assert out.tokens_in == 300 and out.tokens_out == 700
    # 300/1000*0.001 + 700/1000*0.002 = 0.0017
    assert out.cost_usd == pytest.approx(0.0017)
    assert out.note is None


async def test_direct_malformed_content_falls_back_to_none(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    async def fake_chat(payload, *, api_key):
        return {
            "choices": [{"message": {"content": "I could not decide."}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }

    monkeypatch.setattr(analyzer, "_deepseek_chat", fake_chat)
    out = await analyze_async("p")
    assert out.structured is None
    assert out.note == "no new signal"
    assert out.text == "I could not decide."  # raw kept for the trace/history


async def test_direct_transient_error_degrades(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    async def boom(payload, *, api_key):
        raise analyzer.TransientProposerError("rate limited")

    monkeypatch.setattr(analyzer, "_deepseek_chat", boom)
    out = await analyze_async("p")
    assert out.structured is None and out.cost_usd == 0.0 and out.note == "no new signal"


async def test_direct_missing_key_raises(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "direct")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(analyzer.ProposerError, match="DEEPSEEK_API_KEY"):
        await analyze_async("p")
