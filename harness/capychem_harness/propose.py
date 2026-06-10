"""Harness-side Graph-GA proposer (runs under the pinned Python 3.10 venv).

Reads a scored population on stdin, runs ONE Jensen Graph-GA reproduce step
(fitness-weighted parent selection -> crossover -> probabilistic mutate), and
writes the offspring (with parent provenance) as a single JSON line on stdout.
Reached only via subprocess from modern code — never imported.

Request  (stdin) : {"population": [{"smiles": "...", "score": 0.61}, ...],
                    "n_offspring": 32, "mutation_rate": 0.01, "seed": 42}
Response (stdout): {"offspring": [{"smiles": "...", "parents": [i, j]}, ...],
                    "error": null}

`parents` are indices into the request `population` array (the two crossover
parents). A generation may return FEWER than n_offspring offspring: crossover can
fail RDKit ring/validity checks and yield nothing for a slot. On failure:
exit code 1 and {"offspring": [], "error": "<message>"}.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

# Running a script BY PATH puts the script's own dir (…/capychem_harness/) on
# sys.path[0], not the harness root — so `capychem_harness` is not importable.
# Add the harness root (parents[1] of this file = harness/) so the package import
# below resolves. The harness is package=false / not installed, so this is needed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Same discipline as score.py: capture the real stdout, redirect Python-level
# stdout to stderr so RDKit/numpy chatter cannot corrupt the JSON response.
_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr


def _emit(payload: dict, code: int = 0) -> None:
    json.dump(payload, _REAL_STDOUT)
    _REAL_STDOUT.write("\n")
    _REAL_STDOUT.flush()
    sys.exit(code)


def _err(msg: str) -> None:
    _emit({"offspring": [], "error": msg}, code=1)


def main() -> None:
    try:
        req = json.loads(sys.stdin.read())
        population = list(req["population"])
        n_offspring = int(req["n_offspring"])
        mutation_rate = float(req["mutation_rate"])
        seed = int(req["seed"])
    except (ValueError, KeyError, TypeError) as exc:
        _err(f"Send JSON with 'population', 'n_offspring', 'mutation_rate', 'seed': {exc}")
        return

    try:
        import numpy as np
        from rdkit import Chem

        from capychem_harness.graph_ga import crossover as co
        from capychem_harness.graph_ga import mutate as mu
    except Exception as exc:  # noqa: BLE001 - surface any import failure to caller
        _err(f"Install numpy + rdkit in the harness env (uv sync in harness/): {exc}")
        return

    # Deterministic per the request seed (modern side passes base_seed + gen_index).
    random.seed(seed)
    np.random.seed(seed)

    # Parse parents to Mols; keep the original population index for provenance.
    mols = []
    weights = []
    indices = []
    for i, member in enumerate(population):
        mol = Chem.MolFromSmiles(member["smiles"])
        if mol is None:
            continue
        mols.append(mol)
        weights.append(max(float(member["score"]), 0.0))
        indices.append(i)

    if len(mols) < 2:
        _err("Need at least two valid parents to run crossover")
        return

    # Fitness-weighted selection probabilities (Jensen make_mating_pool).
    total = sum(weights)
    probs = [w / total for w in weights] if total > 0 else [1.0 / len(weights)] * len(weights)

    offspring = []
    for _ in range(n_offspring):
        a, b = (int(x) for x in np.random.choice(len(mols), size=2, p=probs, replace=True))
        child = co.crossover(mols[a], mols[b])
        if child is None:
            continue
        child = mu.mutate(child, mutation_rate)
        if child is None:
            continue
        smi = Chem.MolToSmiles(child)
        if not smi:
            continue
        offspring.append({"smiles": smi, "parents": [indices[a], indices[b]]})

    _emit({"offspring": offspring, "error": None})


if __name__ == "__main__":
    main()
