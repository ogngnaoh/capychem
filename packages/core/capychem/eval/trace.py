"""One analyzer+propose snapshot per generation, for offline diagnosis of why the
analyzer hypothesis helps or hurts. Capture-only: never read by the loop itself
(trace_sink=None keeps the run byte-identical). Every score here is an in-silico
oracle score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GenerationTrace:
    generation: int
    summary_top: list[tuple[str, float]]
    summary_bottom: list[tuple[str, float]]
    recent_top10_means: list[float]
    prior_structured: dict[str, Any] | None
    analyzer_raw: str
    analyzer_structured: dict[str, Any] | None
    prompt_used: str
    prompt_unconditioned: str


def trace_to_dict(t: GenerationTrace) -> dict[str, Any]:
    """JSON-safe dict (tuples -> lists) for the --capture-analyzer-traces dump."""
    return {
        "generation": t.generation,
        "summary_top": [[s, sc] for s, sc in t.summary_top],
        "summary_bottom": [[s, sc] for s, sc in t.summary_bottom],
        "recent_top10_means": list(t.recent_top10_means),
        "prior_structured": t.prior_structured,
        "analyzer_raw": t.analyzer_raw,
        "analyzer_structured": t.analyzer_structured,
        "prompt_used": t.prompt_used,
        "prompt_unconditioned": t.prompt_unconditioned,
    }
