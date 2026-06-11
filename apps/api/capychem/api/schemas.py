"""Pydantic models for the REST + WS surface (request bodies, snapshot, events)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    task: str = "qed"
    budget: int = Field(gt=0)  # FR-015
    seed: int = 42
    pop_size: int = Field(default=100, gt=1)  # crossover needs two parents
    offspring: int = Field(default=32, gt=0)
    mutation_rate: float = 0.01
    plateau_window: int = 5
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


class GenerationCompleteEvent(BaseModel):
    type: Literal["generation.complete"] = "generation.complete"
    generation_index: int
    best_score: float
    oracle_calls_used: int
    top_k: list[TopMolecule]


class RunCompleteEvent(BaseModel):
    type: Literal["run.complete"] = "run.complete"
    run_id: int
    status: str
    summary: dict[str, Any] | None
