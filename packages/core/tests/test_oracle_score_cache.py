"""Persistent, cross-run oracle-score cache (milestone 08 slice 04).

Covers: cache.py hit/miss/canonicalization/version-invalidation at the module level,
then the score node's exploratory-mode wiring (uncounted free hits, cross-run
sharing, benchmark-mode bypass) and hit-rate observability.
"""

from __future__ import annotations

from typing import Any

import pytest
from capychem import cache as cache_mod
from capychem.db.models import Base
from capychem.loop import graph as graph_mod
from capychem.oracle import OracleResult
from capychem.validate import ValidCandidate
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


# ---------------------------------------------------------------------------
# cache.py module-level behavior
# ---------------------------------------------------------------------------


async def test_lookup_miss_on_empty_cache(sm) -> None:  # type: ignore[no-untyped-def]
    async with sm() as session:
        hits = await cache_mod.lookup_many(session, "pytdc:v1", "qed", ["CCO"])
    assert hits == {}


async def test_record_then_lookup_is_a_hit(sm) -> None:  # type: ignore[no-untyped-def]
    async with sm() as session:
        await cache_mod.record_many(session, "pytdc:v1", "qed", [("CCO", 0.42, 5)])
    async with sm() as session:
        hits = await cache_mod.lookup_many(session, "pytdc:v1", "qed", ["CCO"])
    assert hits == {"CCO": (0.42, 5)}


async def test_canonicalization_collapses_smiles_variants(sm) -> None:  # type: ignore[no-untyped-def]
    """Two distinct SMILES strings for the same molecule (ethanol) share one entry."""
    async with sm() as session:
        await cache_mod.record_many(session, "pytdc:v1", "qed", [("CCO", 0.42, 5)])
    async with sm() as session:
        # "OCC" is a different string, same molecule (ethanol) -- canonicalizes to "CCO".
        hits = await cache_mod.lookup_many(session, "pytdc:v1", "qed", ["OCC"])
    assert hits == {"OCC": (0.42, 5)}


async def test_version_bump_invalidates(sm) -> None:  # type: ignore[no-untyped-def]
    async with sm() as session:
        await cache_mod.record_many(session, "pytdc:v1", "qed", [("CCO", 0.42, 5)])
    async with sm() as session:
        hits = await cache_mod.lookup_many(session, "pytdc:v2", "qed", ["CCO"])
    assert hits == {}  # a new oracle_key never matches the old entry


async def test_objective_key_plain_vs_composed() -> None:
    assert cache_mod.objective_key(task="qed", objective_json=None) == "qed"
    h1 = cache_mod.objective_key(task="qed", objective_json={"terms": [{"oracle": "pmo"}]})
    h2 = cache_mod.objective_key(task="qed", objective_json={"terms": [{"oracle": "pmo"}]})
    h3 = cache_mod.objective_key(task="qed", objective_json={"terms": [{"oracle": "jnk3"}]})
    assert h1 == h2  # stable
    assert h1 != h3  # distinct objectives -> distinct keys
    assert h1 != "qed"  # a composed objective never collides with a plain task name


async def test_record_many_race_is_harmless(sm) -> None:  # type: ignore[no-untyped-def]
    """A duplicate-key write (simulating two runs discovering the same new molecule
    at once) doesn't raise -- first writer wins, the rest of the batch still lands."""
    async with sm() as session:
        await cache_mod.record_many(
            session, "pytdc:v1", "qed", [("CCO", 0.1, 1), ("CCN", 0.2, 2)]
        )
        # Re-record CCO (a collision) alongside a genuinely new molecule.
        await cache_mod.record_many(
            session, "pytdc:v1", "qed", [("CCO", 0.9, 9), ("CCC", 0.3, 3)]
        )
    async with sm() as session:
        hits = await cache_mod.lookup_many(session, "pytdc:v1", "qed", ["CCO", "CCN", "CCC"])
    assert hits["CCO"] == (0.1, 1)  # first writer's value wins, no crash
    assert hits["CCN"] == (0.2, 2)
    assert hits["CCC"] == (0.3, 3)  # the new one in the colliding batch still lands


# ---------------------------------------------------------------------------
# score() node wiring
# ---------------------------------------------------------------------------


def _score_state(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_id": 1,
        "gen_index": 1,
        "task": "qed",
        "budget": 100,
        "mol_buffer": set(),
        "run_trace_id": None,
        "gen_span_id": None,
        "_fallback_validated": [],
    }
    base.update(over)
    return base


def _fake_score_counting(calls: list[list[str]]):  # type: ignore[no-untyped-def]
    async def fake(smiles: list[str], task: str) -> list[OracleResult]:
        calls.append(list(smiles))
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=7, cost_usd=0.0)
            for s in smiles
        ]

    return fake


async def test_exploratory_cache_hit_is_free_and_uncounted(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cache_mod, "pytdc_version", lambda: "v1")
    calls: list[list[str]] = []
    monkeypatch.setattr(graph_mod, "score_batch_async", _fake_score_counting(calls))

    async with sm() as session:
        await cache_mod.record_many(session, "pytdc:v1", "qed", [("CCO", 0.99, 3)])

    state = _score_state(
        mode="exploratory",
        validated=[ValidCandidate("CCO", None), ValidCandidate("CCN", None)],
    )
    out = await graph_mod.score(state, sm)  # type: ignore[arg-type]

    # Only the cache MISS (CCN) reached the oracle.
    assert calls == [["CCN"]]
    # The cache hit (CCO) does NOT consume the run's oracle-call budget.
    assert out["mol_buffer"] == {"CCN"}
    assert out["calls_used"] == 1
    # Both candidates are still usable (population continuity): CCO's score came
    # straight from the cache at $0 cost.
    scored_by_smiles = {c.smiles: (sc, cost) for c, sc, cost in out["_scored"]}
    assert scored_by_smiles["CCO"] == (0.99, 0.0)
    assert scored_by_smiles["CCN"] == (0.5, 0.0)


async def test_exploratory_cache_miss_writes_back_for_reuse(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cache_mod, "pytdc_version", lambda: "v1")
    calls: list[list[str]] = []
    monkeypatch.setattr(graph_mod, "score_batch_async", _fake_score_counting(calls))

    state = _score_state(mode="exploratory", validated=[ValidCandidate("CCO", None)])
    out = await graph_mod.score(state, sm)  # type: ignore[arg-type]
    assert calls == [["CCO"]]
    assert out["calls_used"] == 1  # a genuine (paid) miss IS counted

    async with sm() as session:
        hits = await cache_mod.lookup_many(session, "pytdc:v1", "qed", ["CCO"])
    # wall_ms is 0 -- matches _persist's existing OracleCall.wall_ms=0 convention
    # (real wall-clock isn't tracked anywhere in this codebase today).
    assert hits == {"CCO": (0.5, 0)}  # written back so a later run/gen reuses it


async def test_cross_run_sharing(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Run B reuses run A's cached score for the same molecule under the same
    oracle + objective -- the oracle is never called a second time."""
    monkeypatch.setattr(cache_mod, "pytdc_version", lambda: "v1")
    calls: list[list[str]] = []
    monkeypatch.setattr(graph_mod, "score_batch_async", _fake_score_counting(calls))

    run_a = _score_state(
        run_id=1, mode="exploratory", validated=[ValidCandidate("c1ccccc1", None)]
    )
    out_a = await graph_mod.score(run_a, sm)  # type: ignore[arg-type]
    assert calls == [["c1ccccc1"]]
    assert out_a["calls_used"] == 1

    # A fresh run (different run_id, empty mol_buffer of its own) targeting the SAME
    # task later scores the SAME molecule.
    run_b = _score_state(
        run_id=2, mode="exploratory", validated=[ValidCandidate("c1ccccc1", None)]
    )
    out_b = await graph_mod.score(run_b, sm)  # type: ignore[arg-type]
    assert calls == [["c1ccccc1"]]  # NOT called again -- served from run A's cache
    assert out_b["calls_used"] == 0  # free hit, run B's own budget untouched
    assert out_b["_scored"][0][1] == 0.5


async def test_benchmark_mode_never_touches_cache(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """mode='benchmark' bypasses the cache entirely: every candidate is scored via
    the oracle every time, and nothing is ever written to (or read from) the table --
    the trajectory is identical whether the cache table exists or not (G1/G6)."""
    monkeypatch.setattr(cache_mod, "pytdc_version", lambda: "v1")
    calls: list[list[str]] = []
    monkeypatch.setattr(graph_mod, "score_batch_async", _fake_score_counting(calls))

    state1 = _score_state(mode="benchmark", validated=[ValidCandidate("CCO", None)])
    out1 = await graph_mod.score(state1, sm)  # type: ignore[arg-type]
    assert calls == [["CCO"]]
    assert out1["calls_used"] == 1

    # Same molecule again, benchmark mode: scored again (no cache short-circuit) --
    # cross-generation dedup within THIS run's own mol_buffer still applies (slice
    # 05), so simulate a fresh call as if it were a different run/buffer.
    state2 = _score_state(mode="benchmark", validated=[ValidCandidate("CCO", None)])
    out2 = await graph_mod.score(state2, sm)  # type: ignore[arg-type]
    assert calls == [["CCO"], ["CCO"]]  # scored AGAIN -- no cache hit in benchmark mode
    assert out2["calls_used"] == 1

    async with sm() as session:
        hits = await cache_mod.lookup_many(session, "pytdc:v1", "qed", ["CCO"])
    assert hits == {}  # benchmark mode never wrote to the cache either


async def test_no_mode_bypasses_cache_same_as_benchmark(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An absent 'mode' key (existing tests, the CLI path) behaves like benchmark:
    the cache is never consulted even when a sessionmaker is passed."""
    monkeypatch.setattr(cache_mod, "pytdc_version", lambda: "v1")
    calls: list[list[str]] = []
    monkeypatch.setattr(graph_mod, "score_batch_async", _fake_score_counting(calls))
    state = _score_state(validated=[ValidCandidate("CCO", None)])  # no "mode" key
    out = await graph_mod.score(state, sm)  # type: ignore[arg-type]
    assert calls == [["CCO"]]
    assert out["calls_used"] == 1


async def test_hit_rate_is_observable_via_langfuse_span(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The score node reports cache_hits/cache_misses onto its Langfuse span
    (trace.update_span) every generation that touched the cache -- the "metric" leg
    of "Hit-rate observable (log/metric/Langfuse)". Asserted via a monkeypatched
    trace.update_span rather than caplog: a real-log assertion is order-fragile in
    this suite because test_migrations.py runs Alembic's env.py, whose fileConfig()
    call disables any logger instantiated before it (a pre-existing, unrelated
    stdlib-logging hazard, not something this slice's tests should depend on)."""
    monkeypatch.setattr(cache_mod, "pytdc_version", lambda: "v1")
    calls: list[list[str]] = []
    monkeypatch.setattr(graph_mod, "score_batch_async", _fake_score_counting(calls))
    span_updates: list[dict[str, Any]] = []
    monkeypatch.setattr(
        graph_mod.trace, "update_span", lambda span_id, **kw: span_updates.append(kw)
    )
    async with sm() as session:
        await cache_mod.record_many(session, "pytdc:v1", "qed", [("CCO", 0.99, 3)])

    state = _score_state(
        mode="exploratory",
        validated=[ValidCandidate("CCO", None), ValidCandidate("CCN", None)],
    )
    await graph_mod.score(state, sm)  # type: ignore[arg-type]

    assert {"cache_hits": 1, "cache_misses": 1} in span_updates
