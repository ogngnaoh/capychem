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
