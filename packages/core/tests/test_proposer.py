"""Env-selected proposer backend + cost mapping (milestone-02 slice 03)."""

from __future__ import annotations

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
                {"raw": "```\nCCO\n```", "tokens_in": 1000, "tokens_out": 500}
                for _ in range(n)
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
