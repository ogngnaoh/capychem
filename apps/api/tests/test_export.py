"""Slice 07-07: CSV + SDF lineage export (RDKit round-trips the SDF)."""

from __future__ import annotations

import io

import httpx
from capychem.api.routes_runs import router
from capychem.db.models import AnalyzerHypothesis, Base, Candidate, Generation, Run
from fastapi import FastAPI
from rdkit import Chem
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def _seeded_app() -> FastAPI:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        s.add(
            Run(
                id=1,
                task="qed",
                mutation_strategy="llm",
                status="exhausted",
                budget=100,
                plateau_window=5,
                pop_size=10,
                offspring=4,
                mutation_rate=0.01,
                seed=42,
                mode="benchmark",
            )
        )
        await s.flush()
        s.add_all(
            [
                Generation(id=10, run_id=1, index=0, proposer_used="starting"),
                Generation(id=11, run_id=1, index=1, proposer_used="llm"),
            ]
        )
        s.add(
            AnalyzerHypothesis(
                run_id=1,
                after_generation_index=0,
                text="focus amides",
                structured_json={"focus": "amide"},
            )
        )
        await s.flush()
        s.add_all(
            [
                Candidate(
                    id=100,
                    generation_id=10,
                    smiles="CCO",
                    proposer="starting",
                    valid=True,
                    score=0.4,
                    quality_json={
                        "valid": True,
                        "qed": 0.41,
                        "sa_score": 1.98,
                        "lipinski_pass": True,
                        "pains": False,
                    },
                ),
                Candidate(
                    id=101,
                    generation_id=11,
                    smiles="c1ccccc1",
                    parent_candidate_id=100,
                    proposer="llm",
                    valid=True,
                    score=0.5,
                    quality_json={
                        "valid": True,
                        "qed": 0.44,
                        "sa_score": 1.0,
                        "lipinski_pass": True,
                        "pains": False,
                    },
                ),
            ]
        )
        await s.commit()
    app = FastAPI()
    app.include_router(router)
    app.state.sessionmaker = sm
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_csv_export_has_lineage_and_quality_columns() -> None:
    app = await _seeded_app()
    async with _client(app) as c:
        r = await c.get("/runs/1/export.csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    header = lines[0]
    for col in (
        "candidate_id",
        "generation",
        "parent_candidate_id",
        "smiles",
        "score",
        "qed",
        "sa_score",
        "lipinski_pass",
        "pains",
        "hypothesis_at_birth",
    ):
        assert col in header
    assert len(lines) == 3  # header + 2 candidates
    # the gen-1 candidate was born under the hypothesis after gen 0
    assert "focus amides" in r.text


async def test_sdf_export_round_trips_through_rdkit() -> None:
    app = await _seeded_app()
    async with _client(app) as c:
        r = await c.get("/runs/1/export.sdf")
        assert r.status_code == 200
    supplier = Chem.ForwardSDMolSupplier(io.BytesIO(r.text.encode()))
    mols = [m for m in supplier if m is not None]
    assert len(mols) == 2  # both candidates round-trip
    props = {m.GetProp("candidate_id"): m for m in mols}
    assert props["101"].GetProp("score") == "0.5"
    assert props["101"].GetProp("qed") == "0.44"


async def test_export_404_for_unknown_run() -> None:
    app = await _seeded_app()
    async with _client(app) as c:
        assert (await c.get("/runs/999/export.csv")).status_code == 404
        assert (await c.get("/runs/999/export.sdf")).status_code == 404
