"""Pydantic models for the REST + WS surface (request bodies, snapshot, events)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from capychem.eval.tasks import PMO_TASKS
from capychem.objective import Objective
from pydantic import BaseModel, Field, field_validator
from rdkit import Chem, RDLogger

# Silence per-molecule parse warnings; invalidity is signalled by a None mol
# (mirrors packages/core/capychem/validate.py's convention).
RDLogger.DisableLog("rdApp.*")


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
    # Operator bring-your-own starting compounds (07-02, FR-001). A non-empty list
    # forces mode=exploratory (server-derived at the route). Distinct from the
    # integer RNG ``seed`` above — a population source, never the RNG seed (G6).
    seed_smiles: list[str] | None = None
    # Composed multi-term objective spec (07-04). Present ⇒ mode=exploratory. Scoring
    # routes through the objective instead of the single task; None = benchmark.
    objective_json: dict[str, Any] | None = None

    @field_validator("task")
    @classmethod
    def _task_must_be_pmo(cls, v: str) -> str:
        if v not in PMO_TASKS:
            raise ValueError(f"Choose a PMO task from the 23-task surface; got {v!r}.")
        return v

    @field_validator("seed_smiles")
    @classmethod
    def _seeds_must_be_valid_smiles(cls, v: list[str] | None) -> list[str] | None:
        """Authoritative RDKit gate at the /runs boundary (a client can POST here
        directly, so this cannot rely on the intent-preview check). Empties are
        dropped; an all-empty/`[]` list collapses to None so it stays benchmark."""
        if v is None:
            return None
        cleaned = [s.strip() for s in v if s.strip()]
        if not cleaned:
            return None
        invalid = [s for s in cleaned if Chem.MolFromSmiles(s) is None]
        if invalid:
            raise ValueError(f"Validate seed SMILES via RDKit; these did not parse: {invalid}")
        return cleaned

    @field_validator("objective_json")
    @classmethod
    def _objective_must_be_well_formed(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Structural gate at the /runs boundary — a bad objective (unknown oracle,
        empty terms, non-positive weight, unknown transform) is rejected here rather
        than failing mid-run."""
        if v is None:
            return None
        try:
            Objective.from_json(v)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Invalid objective spec: {exc}") from exc
        return v


class ObjectiveValidateRequest(BaseModel):
    """POST /objective/validate: preview a composed objective on a probe set (07-04)."""

    spec: dict[str, Any]
    smiles: list[str] = Field(default_factory=lambda: ["c1ccccc1"])


class ObjectiveValidateResult(BaseModel):
    smiles: str
    score: float | None  # None = the objective could not score it (invalid / penalized)


class ObjectiveValidateResponse(BaseModel):
    aggregator: str
    n_terms: int
    results: list[ObjectiveValidateResult]


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
    # benchmark|exploratory (07-01). Required, never defaulted: a snapshot with an
    # unknown mode must fail loudly rather than silently claim benchmark-comparable.
    mode: str
    budget: int
    plateau_window: int
    generation_index: int
    oracle_calls_used: int
    best_score: float | None
    top_k: list[TopMolecule]
    auc_curve: list[CurvePoint]
    cost_so_far_usd: float = 0.0
    hypotheses: list[AnalyzerHypothesisOut] = []
    # Langfuse deep link (FR-014); None while a run is live or when unconfigured.
    trace_url: str | None = None
    # Workbench read-fields (milestone 05 slice 03a), all nullable/additive:
    # cumulative valid-SMILES rate from summary_json (None until the run has
    # persisted at least one generation's validation_stats).
    valid_smiles_rate: float | None = None
    # This task's Graph-GA AUC top-10 from the G1 sweep report (None if the task
    # isn't in that report); see capychem.api.ga_baseline.
    graph_ga_baseline: float | None = None
    # Cost breakdown alongside the existing cost_so_far_usd scalar; None if the
    # run has no RunCost row yet.
    llm_cost_usd: float | None = None
    oracle_cost_usd: float | None = None


class RunListItem(BaseModel):
    """Lighter than RunSnapshot for the runs-list view; carries started_at
    (RunSnapshot does not), omits top_k/auc_curve/hypotheses."""

    run_id: int
    task: str
    mutation_strategy: str
    mode: str  # benchmark|exploratory (07-01); required, mirrors RunSnapshot.mode
    status: str
    best_score: float | None
    oracle_calls: int
    budget: int
    started_at: datetime


class CompareRun(BaseModel):
    """One run's side of the compare payload — the subset of RunSnapshot the
    compare view shows (no auc_curve: the overlay is the resampled series)."""

    run_id: int
    task: str
    mode: str  # benchmark|exploratory (07-01); an exploratory run is not AUC-comparable
    status: str
    best_score: float | None
    oracle_calls: int
    budget: int
    cost_so_far_usd: float
    top_k: list[TopMolecule]
    hypotheses: list[AnalyzerHypothesisOut]


class AucOverlayPoint(BaseModel):
    """One x of the shared oracle-call grid; a/b are each run's top-10 mean at
    that x (None before a run's first scored generation)."""

    oracle_calls: int
    a: float | None
    b: float | None


class ComparePayload(BaseModel):
    a: CompareRun
    b: CompareRun
    auc_overlay: list[AucOverlayPoint]


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


# ── Catalog + grounded intent resolution (milestone 05 slice 03a) ───────────


class CatalogTaskOut(BaseModel):
    name: str
    description: str


class CatalogGroupOut(BaseModel):
    group: str
    tasks: list[CatalogTaskOut]


class RefusalOut(BaseModel):
    """One FR-015 guardrail refusal: which field, and why."""

    field: str
    reason: str


class ResolvedPlan(BaseModel):
    task: str
    budget: int
    plateau_window: int
    mutation_strategy: str
    seed_smiles: str | None = None


class IntentResolveRequest(BaseModel):
    text: str
    budget: int | None = None
    seed_smiles: str | None = None


class IntentResolution(BaseModel):
    """POST /intent/resolve response. Grounded to the 23-task PMO catalog only —
    ``matched_task`` is never a name outside ``capychem.eval.tasks.PMO_TASKS``."""

    matched_task: str | None
    confidence: Literal["high", "medium", "low"] | None
    closest_task: str | None
    rationale: str
    resolved_plan: ResolvedPlan | None
    refusals: list[RefusalOut] = []
    cost_usd: float = 0.0
