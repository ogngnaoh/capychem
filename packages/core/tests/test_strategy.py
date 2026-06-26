"""Shared proposer strategy pieces (milestone-02 slice 04)."""

from __future__ import annotations

from capychem import proposer as proposer_mod
from capychem.loop import strategy
from capychem.validate import ValidCandidate


def test_build_prompt_is_deterministic_and_mentions_task_and_population() -> None:
    pop = [("CCO", 0.9), ("c1ccccc1", 0.4)]
    p1 = strategy.build_prompt("jnk3", pop, 5)
    p2 = strategy.build_prompt("jnk3", pop, 5)
    assert p1 == p2
    assert "jnk3" in p1
    assert "CCO" in p1


async def test_propose_llm_async_uses_pinned_temperature_and_seed(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_batch(prompt, n, *, temperature=0.7, seed=0):
        captured.update(prompt=prompt, n=n, temperature=temperature, seed=seed)
        return [
            proposer_mod.ProposalResult(raw="CCO", smiles="CCO", tokens_in=0, tokens_out=0)
            for _ in range(n)
        ]

    monkeypatch.setattr(strategy, "propose_batch_async", fake_batch)
    out = await strategy.propose_llm_async("qed", [("CCO", 0.5)], n=3, seed=11)
    assert len(out) == 3
    assert captured["temperature"] == strategy.LLM_TEMPERATURE
    assert captured["seed"] == 11


def test_propose_llm_sync_bridges_async(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")
    out = strategy.propose_llm_sync("qed", [("CCO", 0.5)], n=4, seed=7)
    assert len(out) == 4
    assert all(isinstance(r, proposer_mod.ProposalResult) for r in out)


def test_ga_fill_wraps_propose_offspring(monkeypatch) -> None:
    from capychem.oracle import Offspring

    def fake_offspring(population, n_offspring, *, mutation_rate, seed, **kw):
        return [Offspring(smiles="CCC", parents=(0, 1)) for _ in range(n_offspring)]

    monkeypatch.setattr(strategy, "propose_offspring", fake_offspring)
    out = strategy.ga_fill([("CCO", 0.5), ("CCN", 0.4)], 3, mutation_rate=0.01, seed=5)
    assert out == [("CCC", (0, 1)), ("CCC", (0, 1)), ("CCC", (0, 1))]


def test_fallback_fill_backfills_gap_and_dedups(monkeypatch) -> None:
    from capychem.oracle import Offspring

    # GA returns one fresh valid SMILES (CCC) and one that duplicates an existing
    # validated candidate (CCO) -> the duplicate is dropped.
    def fake_offspring(population, n_offspring, *, mutation_rate, seed, **kw):
        return [Offspring(smiles="CCC", parents=(0, 1)), Offspring(smiles="OCC", parents=(0, 1))]

    monkeypatch.setattr(strategy, "propose_offspring", fake_offspring)
    validated = [ValidCandidate(smiles="CCO", parents=None, proposer="llm")]  # canonical "CCO"
    out = strategy.fallback_fill(
        validated, [("CCO", 0.5), ("CCN", 0.4)], target=3, mutation_rate=0.01, seed=5
    )
    smiles = {c.smiles for c in out}
    assert "CCC" in smiles
    assert "CCO" not in smiles  # OCC canonicalizes to CCO -> deduped against the LLM-valid set
    assert all(c.proposer == "graph_ga" for c in out)


def test_fallback_fill_returns_empty_when_no_gap() -> None:
    validated = [ValidCandidate(smiles="CCO", parents=None, proposer="llm")]
    result = strategy.fallback_fill(validated, [("CCO", 0.5)], target=1, mutation_rate=0.01, seed=5)
    assert result == []
