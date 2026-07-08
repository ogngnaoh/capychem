"""Composed multi-term objective (07-04): weighted oracles + transforms -> [0,1].

Each term scores a molecule with a registered ScoringOracle (07-03), maps the raw
value into [0,1] via a transform (so a minimize oracle is normalized to maximize —
the loop/AUC always see maximize-in-[0,1]), and the aggregator combines the weighted
terms into a single [0,1] scalar **by construction** (AUC stays comparable).

PMO terms reuse the loop's harness scorer (dependency-injected ``pmo_scorer``) so the
benchmark path is byte-identical; descriptor terms score locally for free. Budget
stays per-candidate (OD-2): one objective evaluation = one unique oracle call,
regardless of term count.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from capychem.oracle import OracleResult, oracle_executor
from capychem.oracle.registry import available_oracles, get_oracle

PmoScorer = Callable[[list[str], str], Awaitable[list[OracleResult]]]

_AGGREGATORS = ("weighted_sum", "weighted_product")
_TRANSFORM_KINDS = ("identity", "sigmoid", "reverse_sigmoid", "double_sigmoid", "value_map")


def stable_hash(spec: dict[str, Any]) -> str:
    """A stable SHA-256 hex digest of a JSON-serializable objective spec.

    Key order never affects the digest (``sort_keys=True``), so the same objective
    always hashes the same way -- the composed-objective half of the persistent
    oracle-score cache key (milestone 08 slice 04, ``capychem.cache.objective_key``).
    """
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _sigmoid(x: float, low: float, high: float, k: float) -> float:
    # low -> ~0, midpoint -> 0.5, high -> ~1 (logistic scaled to the [low, high] span).
    span = high - low
    if span == 0:
        return 0.0 if x < low else 1.0
    return 1.0 / (1.0 + math.exp(-k * (x - (low + high) / 2.0) / span))


def _double_sigmoid(x: float, low: float, high: float, k: float) -> float:
    # A band: a rising sigmoid at ``low`` times a falling sigmoid at ``high`` — peaks
    # (~1) inside [low, high], ~0 outside.
    rise = 1.0 / (1.0 + math.exp(-k * (x - low)))
    fall = 1.0 / (1.0 + math.exp(-k * (high - x)))
    return rise * fall


def _value_map(x: float, points: list[list[float]]) -> float:
    # Piecewise-linear map through sorted (x, y) points; clamped to the endpoints.
    pts = sorted(points, key=lambda p: p[0])
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def apply_transform(spec: dict[str, Any], x: float) -> float:
    """Map a raw oracle value into [0,1]. Output is always clamped to [0,1] so the
    aggregation invariant holds even for an out-of-range raw value."""
    kind = spec["kind"]
    if kind == "identity":
        return _clamp(x)
    if kind == "sigmoid":
        return _clamp(_sigmoid(x, spec["low"], spec["high"], spec.get("k", 10.0)))
    if kind == "reverse_sigmoid":
        return _clamp(1.0 - _sigmoid(x, spec["low"], spec["high"], spec.get("k", 10.0)))
    if kind == "double_sigmoid":
        return _clamp(_double_sigmoid(x, spec["low"], spec["high"], spec.get("k", 10.0)))
    if kind == "value_map":
        return _clamp(_value_map(x, spec["points"]))
    raise ValueError(f"Unknown transform kind {kind!r}; choose one of {_TRANSFORM_KINDS}.")


@dataclass(frozen=True)
class ObjectiveTerm:
    oracle: str
    weight: float
    transform: dict[str, Any]
    oracle_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ObjectiveResult:
    score: float | None  # None when any term could not score the molecule
    cost_usd: float


@dataclass(frozen=True)
class ObjectiveSpec:
    terms: list[ObjectiveTerm]
    aggregator: str

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> ObjectiveSpec:
        aggregator = d.get("aggregator", "weighted_sum")
        if aggregator not in _AGGREGATORS:
            raise ValueError(f"aggregator must be one of {_AGGREGATORS}; got {aggregator!r}.")
        raw_terms = d.get("terms", [])
        if not raw_terms:
            raise ValueError("An objective needs at least one term.")
        known = available_oracles()
        terms: list[ObjectiveTerm] = []
        for t in raw_terms:
            oracle = t["oracle"]
            if oracle not in known:
                raise ValueError(f"Unknown oracle {oracle!r}; choose one of {known}.")
            kwargs = t.get("oracle_kwargs", {})
            if oracle == "pmo" and "task" not in kwargs:
                raise ValueError("A 'pmo' term needs oracle_kwargs.task (a PMO task name).")
            weight = float(t.get("weight", 1.0))
            if weight <= 0:
                raise ValueError(f"Term weights must be positive; got {weight} for {oracle!r}.")
            transform = t.get("transform", {"kind": "identity"})
            if transform.get("kind") not in _TRANSFORM_KINDS:
                raise ValueError(f"Unknown transform kind {transform.get('kind')!r}.")
            terms.append(
                ObjectiveTerm(
                    oracle=oracle, weight=weight, transform=transform, oracle_kwargs=kwargs
                )
            )
        return cls(terms=terms, aggregator=aggregator)

    def to_json(self) -> dict[str, Any]:
        return {
            "terms": [
                {
                    "oracle": t.oracle,
                    "oracle_kwargs": t.oracle_kwargs,
                    "weight": t.weight,
                    "transform": t.transform,
                }
                for t in self.terms
            ],
            "aggregator": self.aggregator,
        }

    def aggregate(self, values: list[float], weights: list[float]) -> float:
        """Combine per-term [0,1] scores into one [0,1] scalar. A single term returns
        the raw value under both aggregators."""
        total_w = sum(weights)
        if self.aggregator == "weighted_sum":
            return sum(w * v for w, v in zip(weights, values, strict=True)) / total_w
        # weighted geometric mean — stays in [0,1], single term = value^(w/w) = value.
        prod = 1.0
        for v, w in zip(values, weights, strict=True):
            prod *= max(v, 0.0) ** w
        return float(prod ** (1.0 / total_w))


class Objective:
    """A runnable objective: resolves each term's oracle and scores a batch."""

    def __init__(self, spec: ObjectiveSpec) -> None:
        self.spec = spec

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Objective:
        return cls(ObjectiveSpec.from_json(d))

    def to_json(self) -> dict[str, Any]:
        return self.spec.to_json()

    async def evaluate_async(
        self, smiles: list[str], *, pmo_scorer: PmoScorer
    ) -> list[ObjectiveResult]:
        """Score a batch. A ``pmo`` term routes through the injected ``pmo_scorer``
        (the loop's retry-wrapped harness path — cost + backend preserved); every
        other term scores locally in a thread (free). A candidate is ``None`` if any
        term cannot score it; its cost is the sum of the terms' costs."""
        n = len(smiles)
        per_term_scores: list[list[float | None]] = []
        per_term_costs: list[list[float]] = []
        for term in self.spec.terms:
            if term.oracle == "pmo":
                results = await pmo_scorer(smiles, term.oracle_kwargs["task"])
                raw: list[float | None] = [r.score if r.valid else None for r in results]
                costs = [r.cost_usd for r in results]
            else:
                oracle = get_oracle(term.oracle, **term.oracle_kwargs)
                # Bounded pool (m08-05), shared with score_batch_async's harness
                # dispatch — a burst of concurrent evaluate_async calls can never
                # spin up more than CAPYCHEM_ORACLE_THREAD_POOL_SIZE OS threads.
                loop = asyncio.get_running_loop()
                raw = await loop.run_in_executor(oracle_executor(), oracle.score, smiles)
                costs = [0.0] * n
            per_term_scores.append(
                [None if v is None else apply_transform(term.transform, v) for v in raw]
            )
            per_term_costs.append(costs)

        weights = [t.weight for t in self.spec.terms]
        out: list[ObjectiveResult] = []
        for i in range(n):
            vals = [per_term_scores[t][i] for t in range(len(self.spec.terms))]
            cost = sum(per_term_costs[t][i] for t in range(len(self.spec.terms)))
            if any(v is None for v in vals):
                out.append(ObjectiveResult(score=None, cost_usd=cost))
            else:
                clean = [v for v in vals if v is not None]
                out.append(
                    ObjectiveResult(score=self.spec.aggregate(clean, weights), cost_usd=cost)
                )
        return out
