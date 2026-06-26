"""Pure decision helpers for the loop — no DB, no harness, no I/O.

Kept free of side effects so they unit-test in isolation and stay deterministic.
"""

from __future__ import annotations

from typing import Any

from capychem.loop.state import Scored

VALID_SMILES_THRESHOLD = 0.80


def valid_smiles_gate(rate: float, threshold: float = VALID_SMILES_THRESHOLD) -> dict[str, Any]:
    """The milestone-02 >80% valid-SMILES gate. Observational: it reports a verdict,
    it never halts a run (the Graph-GA fallback guarantees throughput)."""
    return {"threshold": threshold, "passed": rate >= threshold}


def trim_to_budget[T](items: list[T], *, budget: int, calls_used: int) -> list[T]:
    """Cap a validated batch to the remaining budget so a generation never
    overshoots (FR-002)."""
    remaining = max(budget - calls_used, 0)
    return items[:remaining]


def _sort_key(m: Scored) -> tuple[float, str]:
    # Descending score; ascending canonical SMILES as a deterministic tiebreak (G6).
    return (-m.score, m.smiles)


def merge_and_truncate(
    population: list[Scored], batch: list[Scored], *, pop_size: int
) -> list[Scored]:
    """Merge offspring + survivors and keep the top ``pop_size`` by score, with a
    deterministic canonical-SMILES tiebreak."""
    merged = sorted([*population, *batch], key=_sort_key)
    return merged[:pop_size]


def stop_reason(
    *,
    calls_used: int,
    budget: int,
    gen_index: int,
    max_generations: int,
    made_progress: bool,
) -> str | None:
    """Return a termination reason, or None to continue.

    Priority: budget exhaustion (FR-002) > max-generations cap > zero forward
    progress (guards against an all-invalid / all-duplicate batch looping forever).
    """
    if calls_used >= budget:
        return "exhausted"
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
) -> dict[str, Any]:
    """Build the (un-authoritative) summary_json. The auc_curve here is the
    running top-10-mean; the canonical AUC lives in packages/core/eval (later
    milestone) — do not treat this as the G1 number.

    When ``validation_stats`` (cumulative {"proposed","valid"}) is supplied, a
    stable ``valid_smiles`` block is added. This is the field milestone 02's
    >80% gate reads; keep its shape stable."""
    top = sorted(population, key=_sort_key)[:top_k]
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
    return summary
