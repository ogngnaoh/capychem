import pytest
from capychem.eval import runner as runner_mod
from capychem.eval.runner import run_reproduction


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
    # `==` not `<=`: the subset form passes vacuously on an empty buffer.
    assert set(res.mol_buffer) == {"CCO", "c1ccccc1"}


def test_patience_stop_terminates_before_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stubbed, harness-free. Seeds score high (0.9); every offspring scores lower
    # (0.1) with a fresh SMILES each call, so new molecules ARE added (not the
    # duplicate path) yet the top-100 mean never improves -> patience drives the
    # stop. budget is large so budget-exhaustion cannot be the cause.
    counter = {"n": 0}

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        from capychem.oracle import OracleResult

        out = []
        for s in smiles:
            score = 0.9 if s in {"CCO", "c1ccccc1"} else 0.1
            out.append(OracleResult(smiles=s, score=score, valid=True, wall_ms=1))
        return out

    def fake_propose(population, n_offspring, **kw):  # type: ignore[no-untyped-def]
        from capychem.oracle import Offspring

        # distinct, valid, ever-lower-scoring offspring (carbon chains): CCC, CCCC, ...
        offs = []
        for _ in range(n_offspring):
            counter["n"] += 1
            offs.append(Offspring(smiles="C" * (counter["n"] + 2), parents=(0, 0)))
        return offs

    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "propose_offspring", fake_propose)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: ["CCO", "c1ccccc1"][:n])

    res = run_reproduction("qed", budget=10000, seed=42, pop_size=2, offspring=3, patience=3)
    # stopped by patience, not by budget exhaustion
    assert res.unique_calls < 10000
    # patience=3 -> at most patience+1 generations past gen 0; comfortably small
    assert res.generations <= 5


def test_smoke_real_harness_unique_budget(harness: None) -> None:
    res = run_reproduction("qed", budget=200, seed=42, pop_size=20, offspring=10)
    assert len(res.mol_buffer) <= 200  # never exceeds unique budget
    assert res.unique_calls == len(res.mol_buffer)
    assert all(0.0 <= score <= 1.0 for score, _ in res.mol_buffer.values())
    # determinism: same seed -> same buffer keys
    res2 = run_reproduction("qed", budget=200, seed=42, pop_size=20, offspring=10)
    assert set(res.mol_buffer) == set(res2.mol_buffer)


def test_llm_strategy_runs_to_budget_on_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    # LLM path, harness-free: stub the LLM proposer + the oracle; no fallback fires
    # because the LLM returns valid SMILES.
    from capychem.eval import runner as runner_mod
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    pool = ["CCO", "c1ccccc1", "CCN", "CCC", "CCCC"]

    def fake_llm_sync(task, population, *, n, seed):
        return [
            ProposalResult(
                raw=pool[i % len(pool)], smiles=pool[i % len(pool)], tokens_in=0, tokens_out=0
            )
            for i in range(n)
        ]

    def fake_score(smiles, task, **kw):
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: pool[:n])

    res = run_reproduction(
        "qed", budget=5, seed=42, pop_size=3, offspring=4, patience=2, mutation_strategy="llm"
    )
    assert res.unique_calls == len(res.mol_buffer)
    assert res.mol_buffer  # produced + scored candidates via the LLM path


def test_llm_validity_rate_is_llm_only(monkeypatch: pytest.MonkeyPatch) -> None:
    # LLM emits 2 valid + 2 invalid each gen; seeds are all valid. The tracked
    # rate must reflect LLM proposals only (seeds excluded) -> 0.5.
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    def fake_llm_sync(task, population, *, n, seed):  # type: ignore[no-untyped-def]
        smis = ["CCO", "c1ccccc1", "not-a-smiles", "@@@@"]
        return [
            ProposalResult(raw=smis[i % 4], smiles=smis[i % 4], tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    seeds = ["CCO", "c1ccccc1", "CCN", "CCC"]
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: seeds[:n])

    res = run_reproduction(
        "qed", budget=20, seed=42, pop_size=4, offspring=4, patience=2, mutation_strategy="llm"
    )
    assert res.llm_proposed > 0
    assert res.llm_valid / res.llm_proposed == 0.5
    assert res.valid_rate == 0.5


def test_graph_ga_run_has_no_valid_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    from capychem.oracle import Offspring, OracleResult

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    def fake_propose(population, n_offspring, **kw):  # type: ignore[no-untyped-def]
        return [Offspring(smiles="C" * (i + 3), parents=(0, 0)) for i in range(n_offspring)]

    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "propose_offspring", fake_propose)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: ["CCO", "c1ccccc1"][:n])

    res = run_reproduction("qed", budget=20, seed=42, pop_size=2, offspring=3, patience=2)
    assert res.valid_rate is None
    assert res.llm_proposed == 0
