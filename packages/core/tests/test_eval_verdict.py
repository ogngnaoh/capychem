import pytest
from capychem.eval import verdict as verdict_mod
from capychem.eval.runner import ReproResult
from capychem.eval.verdict import AnalyzerVerdict, run_analyzer_verdict


def _patch_runner(monkeypatch: pytest.MonkeyPatch, llm_pool: list[str]) -> None:
    from capychem.analyzer import AnalyzerResult
    from capychem.eval import runner as runner_mod
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [
            OracleResult(smiles=s, score=min(0.99, 0.3 + 0.05 * len(s)), valid=True, wall_ms=1)
            for s in smiles
        ]

    def fake_llm(task, population, *, n, seed, hypothesis=None):  # type: ignore[no-untyped-def]
        conditioned = hypothesis is not None and hypothesis.structured is not None
        base = llm_pool[1] if conditioned else llm_pool[0]
        return [
            ProposalResult(raw=base * (i + 1), smiles=base * (i + 1), tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    def fake_analyzer(summary, *, seed):  # type: ignore[no-untyped-def]
        return AnalyzerResult(
            text="focus", structured={"focus": "f", "avoid": ["a"]}, tokens_in=0, tokens_out=0
        )

    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm)
    monkeypatch.setattr(runner_mod, "run_analyzer_sync", fake_analyzer)
    monkeypatch.setattr(runner_mod, "starting_population",
                        lambda nn: ["C", "CC", "CCC", "CCCC", "CCCCC"][:nn])


def test_verdict_shape_and_determinism(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch, llm_pool=["C", "O"])
    v1 = run_analyzer_verdict(
        "qed", budget=40, seed=42, pop_size=3, offspring=4, mutation_rate=0.01
    )
    assert isinstance(v1, AnalyzerVerdict)
    assert v1.task == "qed" and v1.seed == 42 and v1.budget == 40
    assert abs(v1.diff - (v1.with_auc - v1.without_auc)) < 1e-12
    assert v1.helps == (v1.with_auc > v1.without_auc)
    # stub analyzer always parses -> healthy
    assert v1.analyzer_parse_rate == 1.0
    assert v1.parse_rate_healthy is True
    assert v1.analyzer_calls > 0 and v1.analyzer_parsed == v1.analyzer_calls
    # same seed -> identical verdict (G6 on the deterministic stub path)
    v2 = run_analyzer_verdict(
        "qed", budget=40, seed=42, pop_size=3, offspring=4, mutation_rate=0.01
    )
    assert v2 == v1


def test_verdict_arms_differ_when_analyzer_conditions_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # hypothesis-sensitive fake LLM -> with-arm and without-arm explore different
    # molecules -> different buffers -> the verdict is a real comparison, not a no-op.
    _patch_runner(monkeypatch, llm_pool=["C", "O"])
    v = run_analyzer_verdict("qed", budget=60, seed=7, pop_size=3, offspring=4, mutation_rate=0.01)
    assert v.with_unique_calls != v.without_unique_calls or v.with_auc != v.without_auc


def test_parse_rate_healthy_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    # Drive run_reproduction's return directly to pin the 0.8 floor. The with-arm
    # (analyzer=True) carries the parse rate; the without-arm has analyzer off.
    def make(rate: float) -> ReproResult:
        parsed = round(rate * 100)
        return ReproResult(
            mol_buffer={"CCO": (0.5, 1)}, generations=2, unique_calls=1,
            analyzer_calls=100, analyzer_parsed=parsed, analyzer_parse_rate=rate,
        )

    off = ReproResult(mol_buffer={"CCN": (0.4, 1)}, generations=2, unique_calls=1)

    def make_fake(rate: float):  # type: ignore[no-untyped-def]
        def fake_run(task, budget, seed, *, analyzer=False, **kw):  # type: ignore[no-untyped-def]
            return make(rate) if analyzer else off
        return fake_run

    monkeypatch.setattr(verdict_mod, "run_reproduction", make_fake(0.80))
    assert run_analyzer_verdict("qed", budget=100, seed=1).parse_rate_healthy is True

    monkeypatch.setattr(verdict_mod, "run_reproduction", make_fake(0.79))
    v = run_analyzer_verdict("qed", budget=100, seed=1)
    assert v.parse_rate_healthy is False
    assert v.analyzer_parse_rate == 0.79
