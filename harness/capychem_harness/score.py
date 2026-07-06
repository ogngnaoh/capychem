"""Harness-side oracle scorer (runs under the pinned Python 3.10 / PyTDC venv).

This is the ONLY entry point modern code uses, and it uses it via subprocess —
never `import`. Reads a JSON request on stdin, scores SMILES against a PyTDC
oracle, writes a single JSON response line on stdout.

Request  (stdin) : {"task": "qed", "smiles": ["c1ccccc1", ...]}
Response (stdout): {"task": "qed",
                    "results": [{"smiles": "...", "score": 0.44,
                                 "valid": true, "wall_ms": 12}],
                    "error": null}

On failure: exit code 1 and {"task": ..., "results": [], "error": "<message>"}.
"""

from __future__ import annotations

import json
import sys
import time

# Capture the real stdout, then redirect Python-level stdout to stderr so any
# chatter from TDC/RDKit (download notices, warnings) cannot corrupt the JSON
# response. Only _emit() writes to the real stdout.
_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr


def _emit(payload: dict, code: int = 0) -> None:
    json.dump(payload, _REAL_STDOUT)
    _REAL_STDOUT.write("\n")
    _REAL_STDOUT.flush()
    sys.exit(code)


def _pytdc_version() -> str:
    """The pinned legacy PyTDC version (OD-5 provenance). Best-effort — a citable
    manifest wants the real installed version, not a hard-coded constant."""
    try:
        from importlib.metadata import version

        return version("PyTDC")
    except Exception:  # noqa: BLE001 - provenance is best-effort, never fails scoring
        return "unknown"


def _err(msg: str, task: object = None) -> None:
    _emit({"task": task, "results": [], "error": msg}, code=1)


def main() -> None:
    try:
        req = json.loads(sys.stdin.read())
        task = req["task"]
        smiles_list = list(req["smiles"])
    except (ValueError, KeyError, TypeError) as exc:
        _err(f"Send a JSON object with string 'task' and list 'smiles': {exc}")
        return

    try:
        import types

        from rdkit import Chem

        # PyTDC 0.3.6 does `from rdkit.six import iteritems`, but modern RDKit
        # removed the rdkit.six compat shim. Provide a minimal replacement so the
        # legacy oracle module imports cleanly.
        if "rdkit.six" not in sys.modules:
            import rdkit

            six_shim = types.ModuleType("rdkit.six")
            six_shim.iteritems = lambda d, **_: iter(d.items())  # type: ignore[attr-defined]
            sys.modules["rdkit.six"] = six_shim
            rdkit.six = six_shim  # type: ignore[attr-defined]

        # PyTDC 0.3.6's ML-model oracles unpickle scikit-learn ~0.21 models whose
        # module paths were renamed in 0.22. Alias the old paths to the modern ones
        # (sklearn is pinned <1.3 so the estimator dtypes still match). jnk3/gsk3b use
        # a RandomForest; drd2 uses an SVM (sklearn.svm.classes -> sklearn.svm._classes).
        # qed is analytic and never triggers this unpickle.
        import sklearn.ensemble._forest  # noqa: F401
        import sklearn.svm._classes  # noqa: F401
        import sklearn.tree._classes  # noqa: F401

        sys.modules.setdefault("sklearn.ensemble.forest", sys.modules["sklearn.ensemble._forest"])
        sys.modules.setdefault("sklearn.svm.classes", sys.modules["sklearn.svm._classes"])
        sys.modules.setdefault("sklearn.tree.tree", sys.modules["sklearn.tree._classes"])

        from tdc import Oracle
    except Exception as exc:  # noqa: BLE001 - surface any import failure to caller
        _err(f"Install pytdc and rdkit in the harness env (uv sync in harness/): {exc}", task)
        return

    try:
        oracle = Oracle(name=task)
    except Exception as exc:  # noqa: BLE001
        _err(f"Construct a valid PyTDC oracle for task '{task}': {exc}", task)
        return

    results = []
    for smi in smiles_list:
        valid = Chem.MolFromSmiles(smi) is not None
        score = None
        start = time.perf_counter()
        if valid:
            try:
                score = float(oracle(smi))
            except Exception:  # noqa: BLE001 - a scoring failure marks the SMILES invalid
                valid = False
        wall_ms = int((time.perf_counter() - start) * 1000)
        results.append({"smiles": smi, "score": score, "valid": valid, "wall_ms": wall_ms})

    _emit({"task": task, "results": results, "error": None, "pytdc_version": _pytdc_version()})


if __name__ == "__main__":
    main()
