"""Standalone regression for the Graph-GA crossover empty-``RunReactants`` guard.

Runs UNDER the harness interpreter (``harness/.venv``, Python 3.10) — the only
legitimate way to exercise harness internals. Modern code never imports this.

The vendored Jensen GB-GA crossover does ``rxn.RunReactants((fa, fb))[0]`` at two
sites — ``crossover_non_ring`` (the observed ``median2`` crash) and
``crossover_ring``. When the reaction yields no products the tuple is empty and
``[0]`` raises ``IndexError``, which propagates out of ``propose.py`` (no
try/except around ``co.crossover``) and crashes the whole propose subprocess for
that generation. The guard captures the products and skips on empty.

This harness has no pytest (adding it would churn the pinned 3.10 lockfile), so
this is a plain assert-script.

Run: ``harness/.venv/bin/python harness/tests/test_crossover_guard.py``
Exit 0 = pass, non-zero = fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Script-by-path puts THIS dir on sys.path[0]; add the harness root so
# ``capychem_harness`` imports (mirrors propose.py / score.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rdkit import Chem  # noqa: E402

from capychem_harness.graph_ga import crossover as co  # noqa: E402


class _EmptyRxn:
    """A reaction yielding no products — the empty-tuple case that crashed ``[0]``."""

    def RunReactants(self, _reactants: object) -> tuple[()]:
        return ()


def test_crossover_non_ring_guards_empty_runreactants() -> None:
    # Pin ``cut`` to real fragments and force every reaction to yield no products,
    # so we deterministically reach the ``RunReactants((fa, fb))[0]`` site with an
    # empty result. Pre-guard: IndexError. Guarded: clean None.
    frag = Chem.MolFromSmiles("CCC")
    orig_cut = co.cut
    orig_rxn = co.AllChem.ReactionFromSmarts
    co.cut = lambda _mol: (frag, frag)  # type: ignore[assignment]
    co.AllChem.ReactionFromSmarts = lambda *a, **k: _EmptyRxn()  # type: ignore[assignment]
    try:
        parent = Chem.MolFromSmiles("CCCCCCCC")
        result = co.crossover_non_ring(parent, parent)
        assert result is None, f"expected None when no products form, got {result!r}"
    finally:
        co.cut = orig_cut  # type: ignore[assignment]
        co.AllChem.ReactionFromSmarts = orig_rxn  # type: ignore[assignment]


def test_crossover_ring_guards_empty_runreactants() -> None:
    # Same defect at the ring-crossover site. Pin ``cut_ring`` to real fragments so
    # we deterministically reach the line-109 ``RunReactants((fa, fb))[0]`` site.
    frag = Chem.MolFromSmiles("C1CCCCC1")
    orig_cut_ring = co.cut_ring
    orig_rxn = co.AllChem.ReactionFromSmarts
    co.cut_ring = lambda _mol: (frag, frag)  # type: ignore[assignment]
    co.AllChem.ReactionFromSmarts = lambda *a, **k: _EmptyRxn()  # type: ignore[assignment]
    try:
        parent = Chem.MolFromSmiles("C1CCCCC1")  # has a ring -> passes the ring gate
        result = co.crossover_ring(parent, parent)
        assert result is None, f"expected None when no products form, got {result!r}"
    finally:
        co.cut_ring = orig_cut_ring  # type: ignore[assignment]
        co.AllChem.ReactionFromSmarts = orig_rxn  # type: ignore[assignment]


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
        print(f"\n{len(failures)} of {len(tests)} crossover-guard test(s) FAILED")
        return 1
    print(f"\nall {len(tests)} crossover-guard tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
