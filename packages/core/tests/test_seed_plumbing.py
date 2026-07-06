"""Slice 07-02: operator seed SMILES reach the gen-0 population (FR-001).

The integer RNG ``seed`` is a distinct concept and is never touched here — a
custom seed population is a *population source*, not the RNG seed (G6).
"""

from __future__ import annotations

from typing import Any

from capychem.loop import graph as graph_mod
from capychem.loop.seeds import build_seed_population

# --- build_seed_population: canon + dedup + top-up/truncate to pop_size --------


def test_seeds_topped_up_from_shipped_pool_to_pop_size() -> None:
    pop = build_seed_population(["CCO"], pop_size=5)
    assert len(pop) == 5  # 1 operator seed + 4 shipped-pool top-ups
    assert pop[0] == "CCO"  # operator seed leads
    assert len(set(pop)) == 5  # all unique


def test_more_seeds_than_pop_size_are_truncated_no_topup() -> None:
    seeds = ["CCO", "CCN", "CCC", "CCCl", "CCBr"]
    pop = build_seed_population(seeds, pop_size=3)
    assert pop == ["CCO", "CCN", "CCC"]  # first three, canonical, no shipped pool


def test_seeds_are_canonicalized_and_deduped() -> None:
    # "OCC" and "CCO" are the same molecule; the canonical form appears once.
    pop = build_seed_population(["OCC", "CCO"], pop_size=4)
    assert pop[0] == "CCO"
    assert pop.count("CCO") == 1


# --- propose gen-0 branch: operator seeds override the shipped pool ------------


def _gen0_state(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_id": 1,
        "gen_index": 0,
        "task": "qed",
        "pop_size": 4,
        "seed": 42,
        "offspring": 3,
        "mutation_rate": 0.01,
        "mutation_strategy": "graph_ga",
        "population": [],
        "calls_used": 0,
        "run_trace_id": None,
        "gen_span_id": None,
    }
    base.update(over)
    return base


async def test_gen0_uses_operator_seeds_when_present() -> None:
    out = await graph_mod.propose(_gen0_state(seed_smiles=["CCO", "CCN"]))  # type: ignore[arg-type]
    assert out["_proposer"] == "starting"
    smis = [smi for smi, _ in out["proposed"]]
    assert smis[:2] == ["CCO", "CCN"]  # operator seeds lead
    assert len(smis) == 4  # topped up to pop_size


async def test_gen0_falls_back_to_shipped_pool_without_seeds() -> None:
    from capychem.loop.seeds import load_starting_pop

    out = await graph_mod.propose(_gen0_state())  # type: ignore[arg-type]
    assert out["_proposer"] == "starting"
    # No operator seeds -> the unchanged shipped-pool path (byte-identical to before).
    assert out["proposed"] == [(smi, None) for smi in load_starting_pop(4)]


# --- RunConfig + create_run persist seed_smiles/seed_source, not the RNG seed --


async def test_create_run_persists_seed_smiles_and_source() -> None:
    from capychem.db.models import Base, Run
    from capychem.run import RunConfig, create_run
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        run_id = await create_run(
            s,
            RunConfig(
                task="qed", budget=40, seed=42, pop_size=10, offspring=4,
                mutation_rate=0.01, plateau_window=5, max_generations=10,
                mutation_strategy="graph_ga", mode="exploratory",
                seed_smiles=["CCO", "CCN"], seed_source="custom",
            ),
        )
    async with sm() as s:
        row = await s.get(Run, run_id)
        assert row is not None
        assert row.seed_smiles == ["CCO", "CCN"]
        assert row.seed_source == "custom"
        assert row.mode == "exploratory"
        assert row.seed == 42  # the integer RNG seed is a distinct field, untouched
    await engine.dispose()
