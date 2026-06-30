"""Pydantic models for the REST + WS surface (request bodies, snapshot, events)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from capychem.eval.tasks import PMO_TASKS
from pydantic import BaseModel, Field, field_validator


class CreateRunRequest(BaseModel):
    task: str = "qed"
    budget: int = Field(gt=0)  # FR-015
    seed: int = 42
    pop_size: int = Field(default=100, gt=1)  # crossover needs two parents
    offspring: int = Field(default=32, gt=0)
    mutation_rate: float = Field(default=0.01, gt=0, le=1)
    plateau_window: int = Field(default=5, gt=0)
    max_generations: int = Field(default=100, gt=0)
    mutation_strategy: Literal["graph_ga", "llm"] = "graph_ga"

    @field_validator("task")
    @classmethod
    def _task_must_be_pmo(cls, v: str) -> str:
        if v not in PMO_TASKS:
            raise ValueError(
                f"Choose a PMO task from the 23-task surface; got {v!r}."
            )
        return v


class TopMolecule(BaseModel):
    smiles: str
    score: float


class CurvePoint(BaseModel):
    oracle_calls: int
    top10_mean: float


class AnalyzerHypothesisOut(BaseModel):
    after_generation_index: int
    text: str
    structured_json: dict[str, Any] | None = None


class AnalyzerHypothesisEvent(AnalyzerHypothesisOut):
    type: Literal["analyzer.hypothesis"] = "analyzer.hypothesis"


class RunSnapshot(BaseModel):
    run_id: int
    task: str
    status: str
    budget: int
    plateau_window: int
    generation_index: int
    oracle_calls_used: int
    best_score: float | None
    top_k: list[TopMolecule]
    auc_curve: list[CurvePoint]
    cost_so_far_usd: float = 0.0
    hypotheses: list[AnalyzerHypothesisOut] = []


class RunListItem(BaseModel):
    """Lighter than RunSnapshot for the runs-list view; carries started_at
    (RunSnapshot does not), omits top_k/auc_curve/hypotheses."""

    run_id: int
    task: str
    mutation_strategy: str
    status: str
    best_score: float | None
    oracle_calls: int
    budget: int
    started_at: datetime


class GenerationCompleteEvent(BaseModel):
    type: Literal["generation.complete"] = "generation.complete"
    generation_index: int
    best_score: float
    top10_mean: float
    oracle_calls_used: int
    cost_so_far_usd: float = 0.0
    top_k: list[TopMolecule]


class RunCompleteEvent(BaseModel):
    type: Literal["run.complete"] = "run.complete"
    run_id: int
    status: str
    summary: dict[str, Any] | None
