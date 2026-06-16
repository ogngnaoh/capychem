"""Loop state for the LangGraph runtime.

``Scored`` carries a candidate's DB id so offspring can resolve their
``parent_candidate_id`` from the survivor pool. ``LoopState`` is a TypedDict
(LangGraph merges node return dicts into it); it threads Langfuse parent span ids
explicitly so node spans nest across async boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from capychem.validate import ValidCandidate


@dataclass(frozen=True)
class Scored:
    smiles: str  # canonical
    score: float
    candidate_id: int | None = None  # DB id once persisted; enables parent provenance


class LoopState(TypedDict, total=False):
    # config / identity
    run_id: int
    task: str
    budget: int
    seed: int
    pop_size: int
    offspring: int
    mutation_rate: float
    plateau_window: int
    max_generations: int
    # progress
    calls_used: int
    gen_index: int
    population: list[Scored]  # survivor pool, kept at pop_size
    # langfuse ids threaded for nesting across async nodes:
    #   run_trace_id — the run-level trace id (set once at run start)
    #   gen_span_id  — the CURRENT generation span id (updated each generation)
    run_trace_id: str | None
    gen_span_id: str | None
    # transient per-iteration carriers (read across nodes — MUST be declared, or
    # mypy errors `TypedDict has no key`; the leading underscore is just a naming
    # convention for "internal", it does not exempt them from declaration)
    proposed: list[tuple[str, tuple[int, int] | None]]
    validated: list[ValidCandidate]
    _validation_stats: dict[str, int]  # cumulative {"proposed","valid"} across gens
    _proposer: str
    _scored: list[tuple[ValidCandidate, float, float]]  # (candidate, score, cost_usd)
    _made_progress: bool
    auc_curve: list[tuple[int, float]]
    done: bool
    stop_reason: str | None
    summary: dict[str, Any] | None
