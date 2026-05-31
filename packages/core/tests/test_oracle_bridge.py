"""End-to-end test of the harness↔modern subprocess oracle bridge.

This exercises the real harness venv (Python 3.10 + PyTDC 0.3.6) via subprocess —
no mocking. It is the slice's proof that the load-bearing seam works.
"""

from __future__ import annotations

from capychem.oracle import OracleResult, score_smiles


def test_qed_benzene() -> None:
    (result,) = score_smiles(["c1ccccc1"], task="qed")
    assert isinstance(result, OracleResult)
    assert result.valid
    assert result.score is not None
    # RDKit QED for benzene is ~0.4426; allow slack for rdkit version drift.
    assert abs(result.score - 0.4426) < 0.01


def test_invalid_smiles_is_marked_not_valid() -> None:
    benzene, junk = score_smiles(["c1ccccc1", "not_a_smiles"], task="qed")
    assert benzene.valid and benzene.score is not None
    assert not junk.valid
    assert junk.score is None
