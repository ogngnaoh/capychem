"""The score node absorbs a transient oracle blip via a bounded retry (slice 06-06
Part B): one HarnessError followed by a success lets the run complete normally —
it never bubbles up to pause the run."""

from __future__ import annotations

import pytest
from capychem.db.models import Base
from capychem.loop import graph as graph_mod
from capychem.loop.state import LoopState
from capychem.oracle import HarnessError, OracleResult
from capychem.run import RunConfig, create_run
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_transient_blip_is_absorbed_run_completes_normally(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")  # network-free, all-valid

    from capychem import proposer as proposer_mod

    def _distinct_valid_stub(prompt, n, *, temperature, seed):  # type: ignore[no-untyped-def]
        # Distinct, RDKit-valid alkanes (C, CC, CCC, ...) -> no dedup loss, no fallback.
        return [
            proposer_mod.ProposalResult(
                raw="C" * (i + 1), smiles="C" * (i + 1), tokens_in=0, tokens_out=0, cost_usd=0.0
            )
            for i in range(n)
        ]

    monkeypatch.setattr(proposer_mod, "_stub_propose", _distinct_valid_stub)

    # The FIRST score call ever raises HarnessError (a one-off transient blip);
    # every call after that succeeds — a sustained outage is a different scenario
    # (covered by apps/api/tests/test_pause_recover.py).
    calls = {"n": 0}

    async def flaky_score(smiles, task):
        calls["n"] += 1
        if calls["n"] == 1:
            raise HarnessError("transient blip")
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0) for s in smiles
        ]

    async def instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(graph_mod, "score_batch_async", flaky_score)
    monkeypatch.setattr(graph_mod.asyncio, "sleep", instant_sleep)  # skip retry backoff delay

    cfg = RunConfig(
        task="qed",
        budget=50,
        seed=42,
        pop_size=6,
        offspring=4,
        mutation_rate=0.01,
        plateau_window=3,
        max_generations=1,  # exactly one score() call -> isolates the one-call retry assertion
        mutation_strategy="llm",
    )
    async with sm() as s:
        run_id = await create_run(s, cfg)
    g = graph_mod.build_graph(sm)
    initial: LoopState = {
        "run_id": run_id,
        "task": cfg.task,
        "budget": cfg.budget,
        "seed": cfg.seed,
        "pop_size": cfg.pop_size,
        "offspring": cfg.offspring,
        "mutation_rate": cfg.mutation_rate,
        "plateau_window": cfg.plateau_window,
        "max_generations": cfg.max_generations,
        "mutation_strategy": "llm",
        "calls_used": 0,
        "gen_index": 0,
        "population": [],
        "run_trace_id": None,
        "gen_span_id": None,
        "auc_curve": [],
        "done": False,
    }
    # No exception propagates — the score node's retry absorbed the blip.
    final = await g.ainvoke(initial, config={"recursion_limit": 40})

    assert calls["n"] == 2  # 1 failed attempt + 1 successful retry, inside one score() call
    assert final["done"] is True
    assert final["stop_reason"] in {"exhausted", "max_generations", "no_progress", "plateaued"}
    assert final["summary"] is not None
    assert final["summary"]["generations"] >= 1


async def _instant(_seconds: float) -> None:
    return None


async def test_retry_absorbs_sync_graph_ga_blip(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The retry covers the SYNC Graph-GA subprocess calls (strategy.ga_fill /
    fallback_fill), not just async scoring — a one-off transient HarnessError from
    a sync harness call is absorbed. Closes the review finding that propose_offspring
    (the default graph_ga path + FR-005 fallback) had no retry protection."""
    monkeypatch.setattr(graph_mod.asyncio, "sleep", _instant)
    calls = {"n": 0}

    def flaky_ga():  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise HarnessError("transient GA subprocess blip")
        return ["offspring"]

    result = await graph_mod._with_harness_retry(flaky_ga)
    assert result == ["offspring"]
    assert calls["n"] == 2  # 1 failed attempt + 1 successful retry


async def test_retry_absorbs_async_score_blip(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The same helper retries an ASYNC harness call (score_batch_async) — the thunk
    returns an awaitable, which the helper awaits and retries on HarnessError."""
    monkeypatch.setattr(graph_mod.asyncio, "sleep", _instant)
    calls = {"n": 0}

    async def flaky_score():  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise HarnessError("transient score blip")
        return ["scored"]

    result = await graph_mod._with_harness_retry(lambda: flaky_score())
    assert result == ["scored"]
    assert calls["n"] == 2


async def test_retry_reraises_sustained_harness_fault(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A sustained fault exhausts the retry budget and re-raises, so runner._drive
    pauses the run rather than the loop spinning without progress."""
    monkeypatch.setattr(graph_mod.asyncio, "sleep", _instant)
    calls = {"n": 0}

    def always_fail():  # type: ignore[no-untyped-def]
        calls["n"] += 1
        raise HarnessError("sustained outage")

    with pytest.raises(HarnessError, match="sustained outage"):
        await graph_mod._with_harness_retry(always_fail)
    assert calls["n"] == 3  # _HARNESS_RETRY_ATTEMPTS
