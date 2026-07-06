"""Pure decision helpers for the loop — no DB, no harness, no I/O.

Kept free of side effects so they unit-test in isolation and stay deterministic.
"""

from __future__ import annotations

from typing import Any

from capychem.loop.state import AnalyzerSummary, Hypothesis, Scored
from capychem.oracle.protocol import Direction

VALID_SMILES_THRESHOLD = 0.80
PLATEAU_MIN_IMPROVEMENT = 1e-9


def valid_smiles_gate(rate: float, threshold: float = VALID_SMILES_THRESHOLD) -> dict[str, Any]:
    """The milestone-02 >80% valid-SMILES gate. Observational: it reports a verdict,
    it never halts a run (the Graph-GA fallback guarantees throughput)."""
    return {"threshold": threshold, "passed": rate >= threshold}


def trim_to_budget[T](items: list[T], *, budget: int, calls_used: int) -> list[T]:
    """Cap a validated batch to the remaining budget so a generation never
    overshoots (FR-002)."""
    remaining = max(budget - calls_used, 0)
    return items[:remaining]


def _sort_key(m: Scored, direction: Direction = "maximize") -> tuple[float, str]:
    # Best-first: negate for maximize (higher wins), keep sign for minimize (lower
    # wins). Ascending canonical SMILES as a deterministic tiebreak (G6). Default
    # maximize == the pre-07-03 behavior (every benchmark PMO oracle is maximize).
    primary = -m.score if direction == "maximize" else m.score
    return (primary, m.smiles)


def merge_and_truncate(
    population: list[Scored],
    batch: list[Scored],
    *,
    pop_size: int,
    direction: Direction = "maximize",
) -> list[Scored]:
    """Merge offspring + survivors and keep the top ``pop_size`` by score, with a
    deterministic canonical-SMILES tiebreak. ``direction`` ranks a minimize oracle
    correctly (lowest = best) without inverting the benchmark maximize path."""
    merged = sorted([*population, *batch], key=lambda m: _sort_key(m, direction))
    return merged[:pop_size]


def is_plateau(top10_history: list[float], plateau_window: int) -> bool:
    """True when the top-10 mean has not improved over the last ``plateau_window``
    generations (FR-003). The survivor pool is elitist so the history is
    monotonically non-decreasing — "no improvement" means flat (Δ ≤ ε). Needs
    ``plateau_window + 1`` points: the latest vs. the value a full window back."""
    if plateau_window <= 0 or len(top10_history) <= plateau_window:
        return False
    return top10_history[-1] - top10_history[-1 - plateau_window] <= PLATEAU_MIN_IMPROVEMENT


def stop_reason(
    *,
    calls_used: int,
    budget: int,
    gen_index: int,
    max_generations: int,
    made_progress: bool,
    top10_history: list[float] | None = None,
    plateau_window: int = 0,
    constraint_starved_streak: int = 0,
) -> str | None:
    """Return a termination reason, or None to continue.

    Priority: budget exhaustion (FR-002, hard) > constraint-starvation (07-04b) >
    plateau (FR-003) > max-generations cap > zero forward progress (guards an
    all-invalid / all-duplicate batch from looping forever). Plateau outranks the gen
    cap because it is the informative convergence signal (Story 2); the hard budget
    guarantee still wins.

    ``constraint_starved_streak`` > 0 means the current generation produced zero
    constraint-passing candidates. A *sustained* starvation (streak ≥ plateau_window)
    terminates distinctly as ``constraint_starved`` — the constraints are too tight —
    while a *transient* one keeps trying (the GA proposes anew), and is NOT read as
    ``no_progress`` (which would otherwise stop the run after one starved generation
    and mask the real cause).
    """
    if calls_used >= budget:
        return "exhausted"
    if constraint_starved_streak > 0:
        if plateau_window > 0 and constraint_starved_streak >= plateau_window:
            return "constraint_starved"
        if gen_index >= max_generations:
            return "max_generations"
        return None
    if is_plateau(top10_history or [], plateau_window):
        return "plateaued"
    if gen_index >= max_generations:
        return "max_generations"
    if not made_progress:
        return "no_progress"
    return None


def build_summary(
    population: list[Scored],
    auc_curve: list[tuple[int, float]],
    *,
    generations: int,
    oracle_calls: int,
    validation_stats: dict[str, int] | None = None,
    top_k: int = 10,
    direction: Direction = "maximize",
    seed_pop: set[str] | None = None,
) -> dict[str, Any]:
    """Build the (un-authoritative) summary_json. The auc_curve here is the
    running top-10-mean; the canonical AUC lives in packages/core/eval (later
    milestone) — do not treat this as the G1 number.

    When ``validation_stats`` (cumulative {"proposed","valid"}) is supplied, a
    stable ``valid_smiles`` block is added. This is the field milestone 02's
    >80% gate reads; keep its shape stable."""
    top = sorted(population, key=lambda m: _sort_key(m, direction))[:top_k]
    summary: dict[str, Any] = {
        "top_k": [{"smiles": m.smiles, "score": m.score} for m in top],
        "auc_curve": [{"oracle_calls": c, "top10_mean": v} for c, v in auc_curve],
        "generations": generations,
        "oracle_calls": oracle_calls,
    }
    if validation_stats is not None:
        proposed = validation_stats.get("proposed", 0)
        valid = validation_stats.get("valid", 0)
        rate = valid / proposed if proposed else 0.0
        summary["valid_smiles"] = {
            "proposed": proposed,
            "valid": valid,
            "rate": rate,
            "gate": valid_smiles_gate(rate),
        }
    # Run-level trust metrics (07-05). Lazy import so this pure-ish module doesn't pull
    # RDKit/FilterCatalog at import time (build_summary is the only RDKit caller here).
    from capychem.quality import internal_diversity, novelty

    pop_smiles = [m.smiles for m in population]
    summary["diversity"] = internal_diversity(pop_smiles)
    if seed_pop is not None:
        summary["novelty"] = novelty(pop_smiles, seed_pop)
    return summary


def build_analyzer_summary(
    population: list[Scored],
    score_history: list[float],
    prior: Hypothesis | None,
    *,
    k: int = 10,
    direction: Direction = "maximize",
) -> AnalyzerSummary:
    """Compact, deterministic analyzer input: the top-k and bottom-k survivors by
    score, the last 3 top-10-mean values (the recent trajectory), and the prior
    hypothesis. Pure — no I/O — so it reproduces in both loop paths (G6)."""
    ranked = sorted(population, key=lambda m: _sort_key(m, direction))
    top = [(m.smiles, m.score) for m in ranked[:k]]
    bottom = [(m.smiles, m.score) for m in ranked[-k:]] if len(ranked) > k else []
    return AnalyzerSummary(
        top=top, bottom=bottom, recent_top10_means=score_history[-3:], prior=prior
    )
