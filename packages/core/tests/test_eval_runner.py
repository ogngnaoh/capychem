import os

import pytest
from capychem.eval import runner as runner_mod
from capychem.eval.runner import run_reproduction

HARNESS = bool(os.environ.get("CAPYCHEM_HARNESS_PYTHON")) or True  # local default venv exists


def test_memoization_does_not_rescore_known_smiles(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub propose + score so no harness is needed; prove duplicates are not re-scored.
    scored_calls: list[list[str]] = []

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        scored_calls.append(list(smiles))
        from capychem.oracle import OracleResult

        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    # propose always returns the SAME molecule -> after gen 0 they are all known
    def fake_propose(population, n_offspring, **kw):  # type: ignore[no-untyped-def]
        from capychem.oracle import Offspring

        return [Offspring(smiles="CCO", parents=(0, 0)) for _ in range(n_offspring)]

    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "propose_offspring", fake_propose)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: ["CCO", "c1ccccc1"][:n])

    res = run_reproduction("qed", budget=10, seed=42, pop_size=2, offspring=5, patience=2)
    # only the unseen unique SMILES ever reach the scorer; no SMILES scored twice
    all_scored = [s for batch in scored_calls for s in batch]
    assert len(all_scored) == len(set(all_scored))
    assert set(res.mol_buffer) <= {"CCO", "c1ccccc1"}


@pytest.mark.skipif(not HARNESS, reason="needs harness venv")
def test_smoke_real_harness_unique_budget() -> None:
    res = run_reproduction("qed", budget=200, seed=42, pop_size=20, offspring=10)
    assert len(res.mol_buffer) <= 200  # never exceeds unique budget
    assert res.unique_calls == len(res.mol_buffer)
    assert all(0.0 <= score <= 1.0 for score, _ in res.mol_buffer.values())
    # determinism: same seed -> same buffer keys
    res2 = run_reproduction("qed", budget=200, seed=42, pop_size=20, offspring=10)
    assert set(res.mol_buffer) == set(res2.mol_buffer)
