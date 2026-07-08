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

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    # Supports the durable-queue claim query (m08-02): "queued" rows, or "running"
    # rows whose lease has expired, ordered oldest-first by claim_next_run.
    __table_args__ = (Index("ix_run_status_lease", "status", "lease_expires_at"),)

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
    # 32 not 16: the 07-04b terminal status "constraint_starved" is 18 chars. Widened
    # once so future status names have headroom (was String(16) through milestone 06).
    status: Mapped[str] = mapped_column(String(32), default="running")
    # benchmark|exploratory (07-01): server-derived from the run's inputs, never
    # client-set. Only benchmark runs feed the committed G1 numbers.
    mode: Mapped[str] = mapped_column(String(16), default="benchmark")
    # Custom-objective / constraint specs (populated by 07-04); their presence is
    # what forces mode=exploratory via capychem.mode.derive_mode.
    objective_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    constraints_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Operator bring-your-own starting compounds (07-02, FR-001): the raw SMILES the
    # operator supplied (provenance for export/07-07), None for the default pool.
    # seed_source records default|custom. A non-null seed_smiles forces
    # mode=exploratory via derive_mode. Distinct from the integer RNG ``seed``.
    seed_smiles: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    seed_source: Mapped[str] = mapped_column(String(16), default="default")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(default=None)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Reproducibility manifest (07-06, OD-5): git SHA + model id + PyTDC pin + config +
    # trace URL, populated at finalize. Citable provenance for a run's result.
    manifest_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Durable-queue lease (m08-02): the worker id + lease expiry a claimer holds
    # while driving this run, renewed on a heartbeat. All three are None for a
    # freshly-queued or terminal row. capychem.db.queue.claim_next_run treats a
    # "running" row whose lease_expires_at has passed as abandoned (its worker
    # presumably crashed) and reclaims it.
    lease_owner: Mapped[str | None] = mapped_column(String(128), default=None)
    lease_expires_at: Mapped[datetime | None] = mapped_column(default=None)
    heartbeat_at: Mapped[datetime | None] = mapped_column(default=None)
    # Idempotency key (m08-05, SPEC §6.3 POST /runs): a client-supplied
    # ``Idempotency-Key`` header, unique when present. A retried POST with the
    # SAME key returns the existing row instead of minting a second Run; None
    # (no key given) is the unchanged prior behavior -- Postgres allows any
    # number of NULLs under a unique constraint.
    idempotency_key: Mapped[str | None] = mapped_column(String(128), default=None, unique=True)


class Generation(Base):
    __tablename__ = "generations"
    # UNIQUE, not just an index (m08-02b): a UniqueConstraint is index-backed, so
    # lookups stay fast, but it also structurally rejects a duplicate (run_id,
    # index) write -- the backstop against a revived-zombie worker (one whose
    # lease expired and was reclaimed, but which kept driving and tried to
    # persist the same generation index a new owner already wrote).
    __table_args__ = (UniqueConstraint("run_id", "index", name="uq_generation_run_index"),)

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
    # Per-candidate RDKit quality report (07-05): SA/QED/Lipinski/Veber/PAINS/Brenk,
    # computed at persistence. Annotate-only — never affects scoring/selection (OD-4).
    quality_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


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
    # Oracle version (07-06, OD-5): the harness PyTDC pin, backfilled at finalize.
    oracle_version: Mapped[str | None] = mapped_column(String(32), default=None)


class RunCost(Base):
    __tablename__ = "run_costs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), unique=True)
    llm_cost_usd: Mapped[float] = mapped_column(default=0.0)
    oracle_cost_usd: Mapped[float] = mapped_column(default=0.0)
    total_usd: Mapped[float] = mapped_column(default=0.0)


class OracleScoreCache(Base):
    """Persistent, cross-run oracle-score cache (milestone 08 slice 04).

    Keyed on (oracle_key, objective_key, canonical_smiles) -> score. A hit means
    some run already scored this exact molecule under this exact oracle version +
    objective, so the real compute is skippable. Exploratory-mode-only (see
    capychem.cache / the score node in loop/graph.py) -- the benchmark path and the
    eval harness (packages/core/capychem/eval/runner.py) never touch this table, so
    the committed G1 numbers are unaffected by its existence.
    """

    __tablename__ = "oracle_score_cache"
    __table_args__ = (
        UniqueConstraint(
            "oracle_key", "objective_key", "canonical_smiles", name="uq_oracle_score_cache_key"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    oracle_key: Mapped[str] = mapped_column(String(64))  # oracle name + version (invalidation)
    objective_key: Mapped[str] = mapped_column(String(128))  # task name, or a composed-obj hash
    canonical_smiles: Mapped[str] = mapped_column(String(512))
    score: Mapped[float]
    wall_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


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
