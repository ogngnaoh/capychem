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
