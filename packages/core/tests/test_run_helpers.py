from __future__ import annotations

from capychem.db.models import Run
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.run import RunConfig, create_run, finalize_run


async def test_create_and_finalize_run() -> None:
    engine = make_engine()
    await init_schema(engine)
    sm = make_sessionmaker(engine)
    cfg = RunConfig(
        task="qed",
        budget=40,
        seed=42,
        pop_size=20,
        offspring=10,
        mutation_rate=0.01,
        plateau_window=5,
        max_generations=50,
    )
    async with sm() as s:
        run_id = await create_run(s, cfg)
        assert isinstance(run_id, int)
    async with sm() as s:
        await finalize_run(
            s, run_id, {"stop_reason": "exhausted", "summary": {"top_k": [], "generations": 3}}
        )
    async with sm() as s:
        row = await s.get(Run, run_id)
        assert row is not None and row.status == "exhausted"
        assert row.summary_json == {"top_k": [], "generations": 3}
    await engine.dispose()


async def test_create_run_defaults_to_benchmark_mode() -> None:
    engine = make_engine()
    await init_schema(engine)
    sm = make_sessionmaker(engine)
    cfg = RunConfig(
        task="qed",
        budget=40,
        seed=42,
        pop_size=20,
        offspring=10,
        mutation_rate=0.01,
        plateau_window=5,
        max_generations=50,
    )
    async with sm() as s:
        run_id = await create_run(s, cfg)
    async with sm() as s:
        row = await s.get(Run, run_id)
        assert row is not None
        assert row.mode == "benchmark"  # no custom inputs
        assert row.objective_json is None
        assert row.constraints_json is None
    await engine.dispose()


async def test_create_run_persists_exploratory_mode() -> None:
    engine = make_engine()
    await init_schema(engine)
    sm = make_sessionmaker(engine)
    cfg = RunConfig(
        task="qed",
        budget=40,
        seed=42,
        pop_size=20,
        offspring=10,
        mutation_rate=0.01,
        plateau_window=5,
        max_generations=50,
        mode="exploratory",
    )
    async with sm() as s:
        run_id = await create_run(s, cfg)
    async with sm() as s:
        row = await s.get(Run, run_id)
        assert row is not None and row.mode == "exploratory"
    await engine.dispose()
