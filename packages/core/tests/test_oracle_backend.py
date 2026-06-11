"""Env-selected oracle backend + cost mapping (slice 4)."""
from __future__ import annotations

import pytest
from capychem import oracle
from capychem.oracle import OracleResult, score_batch_async


async def test_local_backend_routes_to_subprocess(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_ORACLE_BACKEND", "local")
    captured = {}

    def fake_score(smiles, task, **kw):
        captured["args"] = (tuple(smiles), task)
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=3) for s in smiles]

    monkeypatch.setattr(oracle, "score_smiles", fake_score)
    out = await score_batch_async(["CCO", "c1ccccc1"], "qed")
    assert captured["args"] == (("CCO", "c1ccccc1"), "qed")
    assert [r.cost_usd for r in out] == [0.0, 0.0]  # local is free


async def test_modal_backend_maps_payload_and_cost(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_ORACLE_BACKEND", "modal")
    monkeypatch.setenv("CAPYCHEM_ORACLE_USD_PER_SEC", "0.001")  # 0.001 $/s

    class FakeRemote:
        async def aio(self, smiles, task):
            return [{"smiles": s, "score": 0.5, "valid": True, "wall_ms": 2000} for s in smiles]

    class FakeFn:
        remote = FakeRemote()

    # patch the lookup helper, not modal itself
    monkeypatch.setattr(oracle, "_modal_score_fn", lambda: FakeFn())
    out = await score_batch_async(["CCO"], "qed")
    assert out[0].score == 0.5 and out[0].valid is True
    assert out[0].cost_usd == pytest.approx(0.002)  # 2000 ms = 2 s × 0.001 $/s


async def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_ORACLE_BACKEND", "bogus")
    with pytest.raises(ValueError, match="CAPYCHEM_ORACLE_BACKEND"):
        await score_batch_async(["CCO"], "qed")
