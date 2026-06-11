"""Pydantic models for the REST + WS surface (request bodies, snapshot, events)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    task: Literal["qed"] = "qed"
    budget: int = Field(gt=0)  # FR-015
    seed: int = 42
    pop_size: int = Field(default=100, gt=1)  # crossover needs two parents
    offspring: int = Field(default=32, gt=0)
    mutation_rate: float = Field(default=0.01, gt=0, le=1)
    plateau_window: int = Field(default=5, gt=0)
    max_generations: int = Field(default=100, gt=0)


class TopMolecule(BaseModel):
    smiles: str
    score: float


class CurvePoint(BaseModel):
    oracle_calls: int
    top10_mean: float


class RunSnapshot(BaseModel):
    run_id: int
    task: str
    status: str
    budget: int
    generation_index: int
    oracle_calls_used: int
    best_score: float | None
    top_k: list[TopMolecule]
    auc_curve: list[CurvePoint]
    cost_so_far_usd: float = 0.0


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
