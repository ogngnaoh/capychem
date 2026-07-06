"""figure_canon: the single honest source for the G1 benchmark figures.

Every surface that states the benchmark result (README, run badges, provenance
manifest) derives from here so the framing stays consistent AND honest. The
cardinal sin is "21/23" — 21 beats over a 23-denominator is a real number but it
buries the 2 excluded-for-cause tasks and reads as an overclaim. This test locks
the canon values and forbids that string anywhere the module exposes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capychem import figure_canon


def test_canon_values() -> None:
    c = figure_canon.CANON
    assert c.denominator == 23  # PMO's full single-objective task count
    assert c.comparable == 21  # reproducible, same-seed-Graph-GA-comparable tasks
    assert c.beat_or_matched == 21  # beat-or-matched on every comparable task (21/21)
    assert c.decisive == 9  # decisive margin (>0.1 AUC) subset
    assert c.excluded_for_cause == 2  # oracle-defect tasks removed, not lost
    assert c.bar == 6  # G1 goal: beat Graph-GA on >=6 of 23


def test_excluded_task_names() -> None:
    # The two removed tasks are named so the exclusion is auditable, not hand-waved.
    assert set(figure_canon.CANON.excluded_tasks) == {"valsartan_smarts", "sitagliptin_mpo"}
    # comparable + excluded accounts for all-but-unbanked out of the denominator
    assert figure_canon.CANON.comparable + figure_canon.CANON.excluded_for_cause == 23


def test_headline_is_honest_and_never_21_of_23() -> None:
    headline = figure_canon.headline()
    assert "21" in headline
    assert "23" in headline
    assert "21/23" not in headline
    assert "21 / 23" not in headline


def test_no_exposed_string_contains_21_of_23() -> None:
    # Scan every public string the module can emit; none may collapse to "21/23".
    strings = [
        figure_canon.headline(),
        figure_canon.badge_caption("benchmark"),
        figure_canon.badge_caption("exploratory"),
    ]
    for s in strings:
        assert "21/23" not in s and "21 / 23" not in s


def test_exploratory_badge_says_not_comparable() -> None:
    caption = figure_canon.badge_caption("exploratory")
    assert "not benchmark-comparable" in caption.lower()


def test_verify_against_committed_report_passes() -> None:
    # The canon's comparable count must still match the committed sweep JSON.
    figure_canon.verify_against_report()  # raises on drift


def test_verify_against_report_raises_on_drift(tmp_path: Path) -> None:
    drifted = tmp_path / "drift.json"
    drifted.write_text(json.dumps({"comparable_tasks": 20}))
    with pytest.raises(AssertionError):
        figure_canon.verify_against_report(drifted)


def test_verify_against_missing_report_is_noop(tmp_path: Path) -> None:
    figure_canon.verify_against_report(tmp_path / "does_not_exist.json")  # no raise
