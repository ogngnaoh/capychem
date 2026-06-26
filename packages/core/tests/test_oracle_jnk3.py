"""End-to-end test that the jnk3 PyTDC oracle scores through the re-pinned harness.

jnk3's RandomForest pickle predates the harness's scikit-learn; this proves the
sklearn<1.3 pin + the sys.modules shims make it load and score with a real spread.
Skips when no harness venv is reachable (mirrors the other harness-backed tests).
"""

from __future__ import annotations

from capychem.oracle import score_smiles


def test_jnk3_scores_with_spread(harness: None) -> None:
    # Drug-like seeds score across a range; tiny non-drug-like molecules score ~0.
    # A degenerate (all-equal) result would mean a silently-corrupt cross-version
    # unpickle — which would invalidate the slice-06 beat verdict.
    smis = [
        "c1ccccc1",
        "O=C(O)c1ccccc1",
        "CC(C)Nc1nc(Nc2ccc(N3CCOCC3)cc2)ncc1C(F)(F)F",
        "O=C(Nc1ccc(-c2ccncc2)cc1)c1ccc(F)cc1",
    ]
    results = score_smiles(smis, task="jnk3")
    assert len(results) == len(smis)
    for r in results:
        assert r.valid
        assert r.score is not None
        assert 0.0 <= r.score <= 1.0
    scores = [r.score for r in results if r.score is not None]
    assert max(scores) > min(scores)  # non-degenerate spread
