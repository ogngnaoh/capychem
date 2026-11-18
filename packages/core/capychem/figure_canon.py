"""Consistent figures for the legacy single-seed molecular benchmark.

Every surface that states the benchmark result — run-detail badges and the
provenance manifest — derives its numbers from here, so the framing is
consistent and cannot drift into an overclaim on any one surface.

The figures describe the full-23 sweep in
``data/benchmarks/pmo/g1-full23-10k-seed42.json``:
the sweep report banks 21 comparable rows and 1 excluded row (valsartan_smarts),
because the second excluded task (sitagliptin_mpo) was pre-excluded before the
sweep ran and never banked. Stated honestly the denominator is 23, of which 2 are
excluded-for-cause (oracle defects, caught by a baseline-reproduction check — not
losses) and 21 are comparable, with a beat-or-match on every one of those 21 and a
decisive margin (>0.1 AUC) on 8. The JNK3 margin is 0.09843 and does not pass
that strict threshold.

The forbidden collapse is **"21/23"** — technically 21 beats over a 23 denominator,
but it silently drops the 2 excluded tasks and reads as an overclaim. Never emit it;
``test_figure_canon.py`` fails if this module exposes it. Use ``verify_against_report``
to confirm the comparable count still matches the committed sweep JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_REPORT_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "benchmarks"
    / "pmo"
    / "g1-full23-10k-seed42.json"
)


@dataclass(frozen=True)
class FigureCanon:
    denominator: int  # PMO single-objective task count
    comparable: int  # reproducible tasks comparable to our same-seed Graph-GA control
    beat_or_matched: int  # tasks where the analyzer loop beat-or-matched Graph-GA (of comparable)
    decisive: int  # subset of beats with a decisive margin (>0.1 AUC top-10)
    excluded_for_cause: int  # tasks removed for oracle defects (audited, not losses)
    bar: int  # the G1 goal bar: beat Graph-GA on >= this many of the denominator
    excluded_tasks: tuple[str, ...]  # the named excluded tasks, so the exclusion is auditable


CANON = FigureCanon(
    denominator=23,
    comparable=21,
    beat_or_matched=21,
    decisive=8,
    excluded_for_cause=2,
    bar=6,
    excluded_tasks=("valsartan_smarts", "sitagliptin_mpo"),
)


def headline() -> str:
    """The honest one-line benchmark framing. Never collapses to '21/23'."""
    c = CANON
    return (
        f"Beat or matched vanilla Graph-GA on all {c.comparable} comparable PMO tasks "
        f"(single seed, 10k-call budget) — decisive (>0.1 AUC) on {c.decisive}. "
        f"{c.excluded_for_cause} of {c.denominator} excluded for cause (oracle defects); "
        f"the G1 bar was >= {c.bar} of {c.denominator}."
    )


def badge_caption(mode: Literal["benchmark", "exploratory"]) -> str:
    """Caption for a run's mode badge.

    Benchmark runs are comparable to the committed Graph-GA control; exploratory
    runs (custom seed/oracle/objective/constraint) are explicitly not.
    """
    if mode == "exploratory":
        return "Exploratory run — not benchmark-comparable"
    return "Benchmark run — comparable to the committed Graph-GA control"


def verify_against_report(path: Path | None = None) -> None:
    """Assert the committed sweep backs the comparable and decisive counts.

    Kept out of import so a missing report never breaks importers; call it from a
    test. Raises AssertionError on drift and FileNotFoundError if the default
    runtime fixture is missing. An explicitly absent optional report is skipped.
    """
    report = path or _REPORT_PATH
    if not report.exists():
        if path is not None:
            return
        raise FileNotFoundError(f"Missing committed benchmark fixture: {report}")
    data = json.loads(report.read_text())
    assert data.get("comparable_tasks") == CANON.comparable, (
        f"sweep report comparable_tasks={data.get('comparable_tasks')} != CANON.comparable="
        f"{CANON.comparable}"
    )
    rows = data["rows"]
    assert len(rows) == CANON.comparable, "Comparable row count differs from the benchmark figures"
    decisive = sum(row["llm_auc"] - row["graph_ga_auc"] > 0.1 for row in rows)
    assert decisive == CANON.decisive, (
        f"sweep report decisive count={decisive} != CANON.decisive={CANON.decisive}"
    )
