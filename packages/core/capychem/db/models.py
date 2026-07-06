"""Async SQLAlchemy 2.0 models for CapyChem run state (SPEC §6.2).

Six entities: Run, Generation, Candidate, OracleCall, RunCost, AnalyzerHypothesis
(added milestone-03 slice 01). Schema changes go through Alembic migrations
(packages/core/capychem/db/migrations/) — after changing a model, generate a
revision with `uv run alembic revision --autogenerate -m <message>` and apply it
with `uv run alembic upgrade head`. metadata.create_all (db/session.py) remains
for test bootstrap only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(64))
    budget: Mapped[int]
    mutation_strategy: Mapped[str] = mapped_column(String(32), default="graph_ga")
    plateau_window: Mapped[int]
    max_generations: Mapped[int] = mapped_column(default=100)  # resume needs it (06-07)
    pop_size: Mapped[int]
    offspring: Mapped[int]
    mutation_rate: Mapped[float]
    seed: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="running")
    # benchmark|exploratory (07-01): server-derived from the run's inputs, never
    # client-set. Only benchmark runs feed the committed G1 numbers.
    mode: Mapped[str] = mapped_column(String(16), default="benchmark")
    # Custom-objective / constraint specs (populated by 07-04); their presence is
    # what forces mode=exploratory via capychem.mode.derive_mode.
    objective_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    constraints_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(default=None)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


class Generation(Base):
    __tablename__ = "generations"
    __table_args__ = (Index("ix_generation_run_index", "run_id", "index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    index: Mapped[int]
    proposer_used: Mapped[str] = mapped_column(String(16))  # "starting"|"graph_ga"|"llm"|"mixed"
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(default=None)
    analyzer_hypothesis_id: Mapped[int | None] = mapped_column(
        ForeignKey("analyzer_hypotheses.id", ondelete="SET NULL"), default=None
    )


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[int] = mapped_column(ForeignKey("generations.id", ondelete="CASCADE"))
    smiles: Mapped[str] = mapped_column(String(512))
    parent_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), default=None
    )
    proposer: Mapped[str] = mapped_column(String(16))  # "starting" | "graph_ga" | "llm"
    valid: Mapped[bool] = mapped_column(default=True)
    score: Mapped[float | None] = mapped_column(default=None)


class OracleCall(Base):
    __tablename__ = "oracle_calls"
    __table_args__ = (Index("ix_oraclecall_run_score", "run_id", "score"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    task: Mapped[str] = mapped_column(String(64))
    score: Mapped[float]
    wall_ms: Mapped[int]
    compute_cost_usd: Mapped[float] = mapped_column(default=0.0)  # 0 for local oracle


class RunCost(Base):
    __tablename__ = "run_costs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), unique=True)
    llm_cost_usd: Mapped[float] = mapped_column(default=0.0)
    oracle_cost_usd: Mapped[float] = mapped_column(default=0.0)
    total_usd: Mapped[float] = mapped_column(default=0.0)


class AnalyzerHypothesis(Base):
    __tablename__ = "analyzer_hypotheses"
    __table_args__ = (Index("ix_analyzerhyp_run_after", "run_id", "after_generation_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    after_generation_index: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    structured_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    compute_cost_usd: Mapped[float] = mapped_column(default=0.0)
