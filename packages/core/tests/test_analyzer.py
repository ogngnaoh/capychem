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
