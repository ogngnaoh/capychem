"""Regression: the drd2 PyTDC oracle must score valid molecules.

drd2's model is an SVM pickled under scikit-learn ~0.21, where the class lived at
``sklearn.svm.classes`` (renamed to ``sklearn.svm._classes`` in 0.22). score.py
aliases the RF legacy paths (jnk3/gsk3b) but not the SVM one, so ``load_drd2_model``
raised ``ModuleNotFoundError: No module named 'sklearn.svm.classes'`` for EVERY
molecule -> score.py's bare-except marked every SMILES invalid -> the population
starved -> "Need at least two valid parents to run crossover". This exercises the
real score.py subprocess path end to end.

Runs UNDER the harness interpreter (``harness/.venv``, Python 3.10). This harness
has no pytest, so it is a plain assert-script.

Run: ``harness/.venv/bin/python harness/tests/test_drd2_oracle.py``
Exit 0 = pass, non-zero = fail.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCORE = Path(__file__).resolve().parents[1] / "capychem_harness" / "score.py"


def test_drd2_scores_valid_molecules() -> None:
    req = json.dumps({"task": "drd2", "smiles": ["CCO", "c1ccccc1"]})
    proc = subprocess.run(
        [sys.executable, str(_SCORE)],
        input=req,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"score.py exited {proc.returncode}: {proc.stderr[-400:]}"
    resp = json.loads(proc.stdout)
    assert resp.get("error") is None, resp
    rows = resp["results"]
    assert rows, "no results returned"
    for r in rows:
        assert r["valid"], f"drd2 marked a valid molecule invalid: {r}"
        assert isinstance(r["score"], float), f"drd2 score not a float: {r}"


def main() -> int:
    tests = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure, don't abort
            failures.append((name, exc))
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    if failures:
        print(f"\n{len(failures)} of {len(tests)} drd2-oracle test(s) FAILED")
        return 1
    print(f"\nall {len(tests)} drd2-oracle tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
