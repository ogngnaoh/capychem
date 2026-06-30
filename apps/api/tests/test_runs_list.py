"""Unit tests for the GET /runs list derivation, merge, filter, and sort.

The logic under test is pure (no DB, no app state): `run_list_item` derives a
`RunListItem` from a DB row + an optional live registry snapshot, and
`build_run_list` filters + sorts the merged items. `_db_fields` is the single
derivation shared by the list and the run-detail endpoint (the list == detail
invariant).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from capychem.api.routes_runs import _db_fields, build_run_list, run_list_item
from capychem.api.schemas import RunListItem
from capychem.db.models import Run


def make_run(
    run_id: int,
    *,
    task: str = "qed",
    strategy: str = "graph_ga",
    status: str = "exhausted",
    budget: int = 100,
    started_at: datetime | None = None,
    summary: dict[str, Any] | None = None,
) -> Run:
    return Run(
        id=run_id,
        task=task,
        mutation_strategy=strategy,
        status=status,
        budget=budget,
        plateau_window=5,
        started_at=started_at or datetime(2026, 6, 30, 12, 0, 0),
        summary_json=summary,
    )


def live_snapshot(*, status: str, best: float | None, calls: int) -> dict[str, Any]:
    return {"status": status, "best_score": best, "oracle_calls_used": calls}


# --- run_list_item derivation ------------------------------------------------


def test_run_list_item_uses_live_snapshot_when_present() -> None:
    row = make_run(1, task="jnk3", strategy="llm", budget=200, status="exhausted")
    item = run_list_item(row, live_snapshot(status="running", best=0.51, calls=120))
    assert isinstance(item, RunListItem)
    # live overrides status/best/calls
    assert (item.status, item.best_score, item.oracle_calls) == ("running", 0.51, 120)
    # identity always from the DB row (the live snapshot has no started_at/task/etc.)
    assert item.run_id == 1
    assert item.task == "jnk3"
    assert item.mutation_strategy == "llm"
    assert item.budget == 200
    assert item.started_at == datetime(2026, 6, 30, 12, 0, 0)


def test_run_list_item_falls_back_to_summary_json() -> None:
    row = make_run(
        2,
        status="exhausted",
        summary={"top_k": [{"smiles": "CCO", "score": 0.88}], "oracle_calls": 42},
    )
    item = run_list_item(row, None)
    assert (item.status, item.best_score, item.oracle_calls) == ("exhausted", 0.88, 42)


def test_run_list_item_zero_when_no_summary() -> None:
    row = make_run(3, status="running", summary=None)
    item = run_list_item(row, None)
    assert item.best_score is None
    assert item.oracle_calls == 0
    assert item.status == "running"


# --- list == detail invariant ------------------------------------------------


def test_list_equals_detail_derivation() -> None:
    """The list and the detail endpoint must derive status/best/calls identically.
    Both call `_db_fields`, so the list item must match it for a DB-only row."""
    row = make_run(
        4,
        status="plateaued",
        summary={"top_k": [{"smiles": "c1ccccc1", "score": 0.73}], "oracle_calls": 99},
    )
    item = run_list_item(row, None)
    status, best, calls = _db_fields(row)
    assert (item.status, item.best_score, item.oracle_calls) == (status, best, calls)


# --- build_run_list: sort ----------------------------------------------------


def _ids(items: list[RunListItem]) -> list[int]:
    return [i.run_id for i in items]


def test_default_sort_is_started_at_desc() -> None:
    rows = [
        make_run(1, started_at=datetime(2026, 6, 30, 10, 0, 0)),
        make_run(2, started_at=datetime(2026, 6, 30, 12, 0, 0)),
        make_run(3, started_at=datetime(2026, 6, 30, 11, 0, 0)),
    ]
    out = build_run_list(rows, {}, status=None, task=None, sort="started_at", order="desc")
    assert _ids(out) == [2, 3, 1]


def test_sort_best_score_nulls_last_desc() -> None:
    rows = [
        make_run(1, summary={"top_k": [{"smiles": "C", "score": 0.2}], "oracle_calls": 1}),
        make_run(2, summary=None),  # null best_score
        make_run(3, summary={"top_k": [{"smiles": "C", "score": 0.9}], "oracle_calls": 1}),
    ]
    out = build_run_list(rows, {}, status=None, task=None, sort="best_score", order="desc")
    assert _ids(out) == [3, 1, 2]  # 0.9, 0.2, then null last


def test_sort_best_score_nulls_last_asc() -> None:
    rows = [
        make_run(1, summary={"top_k": [{"smiles": "C", "score": 0.2}], "oracle_calls": 1}),
        make_run(2, summary=None),  # null best_score
        make_run(3, summary={"top_k": [{"smiles": "C", "score": 0.9}], "oracle_calls": 1}),
    ]
    out = build_run_list(rows, {}, status=None, task=None, sort="best_score", order="asc")
    assert _ids(out) == [1, 3, 2]  # 0.2, 0.9, then null STILL last


def test_sort_oracle_calls_desc() -> None:
    rows = [
        make_run(1, summary={"oracle_calls": 10}),
        make_run(2, summary={"oracle_calls": 300}),
        make_run(3, summary={"oracle_calls": 50}),
    ]
    out = build_run_list(rows, {}, status=None, task=None, sort="oracle_calls", order="desc")
    assert _ids(out) == [2, 3, 1]


def test_sort_status_asc() -> None:
    rows = [
        make_run(1, status="running"),
        make_run(2, status="exhausted"),
        make_run(3, status="plateaued"),
    ]
    out = build_run_list(rows, {}, status=None, task=None, sort="status", order="asc")
    assert _ids(out) == [2, 3, 1]  # alphabetical


# --- build_run_list: filter --------------------------------------------------


def test_filter_by_status() -> None:
    rows = [
        make_run(1, status="running"),
        make_run(2, status="exhausted"),
        make_run(3, status="running"),
    ]
    out = build_run_list(rows, {}, status="running", task=None, sort="started_at", order="desc")
    assert set(_ids(out)) == {1, 3}


def test_filter_by_task() -> None:
    rows = [make_run(1, task="qed"), make_run(2, task="jnk3"), make_run(3, task="qed")]
    out = build_run_list(rows, {}, status=None, task="qed", sort="started_at", order="desc")
    assert set(_ids(out)) == {1, 3}


def test_live_overlay_merges_into_list() -> None:
    """A running row's score/calls come from the registry snapshot, not the DB."""
    rows = [
        make_run(1, status="running", summary=None),
        make_run(
            2,
            status="exhausted",
            summary={"top_k": [{"smiles": "C", "score": 0.4}], "oracle_calls": 80},
        ),
    ]
    live_by_id = {1: live_snapshot(status="running", best=0.6, calls=150)}
    out = build_run_list(rows, live_by_id, status=None, task=None, sort="best_score", order="desc")
    by_id = {i.run_id: i for i in out}
    assert (by_id[1].best_score, by_id[1].oracle_calls) == (0.6, 150)  # from live
    assert (by_id[2].best_score, by_id[2].oracle_calls) == (0.4, 80)  # from summary_json
    assert _ids(out) == [1, 2]  # 0.6 > 0.4
