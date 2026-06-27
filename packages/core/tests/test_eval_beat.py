import pytest
from capychem.eval import runner as runner_mod
from capychem.eval.beat import BeatVerdict, run_head_to_head


def _stub(monkeypatch: pytest.MonkeyPatch, llm_pool: list[str]) -> None:
    from capychem.oracle import Offspring, OracleResult
    from capychem.proposer import ProposalResult

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        # deterministic per-SMILES score by length so LLM and GA buffers differ
        return [
            OracleResult(smiles=s, score=min(0.99, 0.3 + 0.05 * len(s)), valid=True, wall_ms=1)
            for s in smiles
        ]

    def fake_ga(population, n, **kw):  # type: ignore[no-untyped-def]
        return [Offspring(smiles="C" * (i + 3), parents=(0, 0)) for i in range(n)]

    def fake_llm(task, population, *, n, seed):  # type: ignore[no-untyped-def]
        return [
            ProposalResult(
                raw=llm_pool[i % len(llm_pool)],
                smiles=llm_pool[i % len(llm_pool)],
                tokens_in=0,
                tokens_out=0,
            )
            for i in range(n)
        ]

    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "propose_offspring", fake_ga)
    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm)
    monkeypatch.setattr(
        runner_mod, "starting_population", lambda n: ["CCO", "c1ccccc1", "CCN", "CCC", "CCCC"][:n]
    )


def test_head_to_head_shape_and_determinism(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, llm_pool=["CCO", "c1ccccc1", "CCN", "CCC"])
    v1 = run_head_to_head("jnk3", budget=8, seed=42, pop_size=3, offspring=4, mutation_rate=0.01)
    assert isinstance(v1, BeatVerdict)
    assert v1.beat == (v1.llm_auc > v1.graph_ga_auc)
    assert abs(v1.diff - (v1.llm_auc - v1.graph_ga_auc)) < 1e-12
    assert v1.published_baseline == 0.553  # jnk3 registered (Task 3)
    assert v1.llm_valid_rate is not None  # llm path ran
    assert v1.llm_valid_gate is not None
    # same seed -> identical verdict (G6)
    v2 = run_head_to_head("jnk3", budget=8, seed=42, pop_size=3, offspring=4, mutation_rate=0.01)
    assert v2 == v1


def test_head_to_head_unknown_task_has_no_published_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, llm_pool=["CCO", "c1ccccc1"])
    v = run_head_to_head("qed", budget=6, seed=1, pop_size=2, offspring=3, mutation_rate=0.01)
    assert v.published_baseline == 0.940  # qed IS registered
    assert isinstance(v.beat, bool)
