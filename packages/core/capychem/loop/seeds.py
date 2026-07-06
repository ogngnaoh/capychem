"""Pure file read of the shipped starting population (no DB, no harness import).

Both the product loop (loop/graph.py) and the headless eval runner
(eval/runner.py) need gen-0 seeds; keeping the read here lets the eval path
import it without pulling in LangGraph / SQLAlchemy.
"""

from __future__ import annotations

from pathlib import Path

from capychem.validate import canonicalize

# packages/core/capychem/loop/seeds.py -> repo root is parents[4].
_STARTING_POP = (
    Path(__file__).resolve().parents[4]
    / "harness"
    / "capychem_harness"
    / "data"
    / "starting_pop.smi"
)


def _all_pop() -> list[str]:
    lines = _STARTING_POP.read_text().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def load_starting_pop(limit: int) -> list[str]:
    """Return up to ``limit`` SMILES from the shipped starting population file."""
    return _all_pop()[:limit]


def build_seed_population(operator_seeds: list[str], pop_size: int) -> list[str]:
    """Gen-0 population from an operator's bring-your-own compounds (07-02, FR-001).

    Canonicalize + dedupe the operator seeds (operator intent leads), then:
    - more than ``pop_size`` seeds -> truncate to the first ``pop_size``;
    - fewer -> top up from the shipped starting pool (skipping anything already
      present) so the population reaches exactly ``pop_size`` where the pool allows.

    Top-up guarantees the ≥2 parents crossover needs and gives the GA material to
    work with. Unparseable seeds are dropped defensively (the ``/runs`` boundary
    already rejects them, so this only fires on a direct/legacy caller)."""
    seen: set[str] = set()
    pop: list[str] = []
    for smi in operator_seeds:
        canon = canonicalize(smi)
        if canon is None or canon in seen:
            continue
        seen.add(canon)
        pop.append(canon)
        if len(pop) >= pop_size:
            return pop[:pop_size]
    # Top up from the shipped pool (its size bounds how far we can fill).
    for smi in _all_pop():
        canon = canonicalize(smi)
        if canon is None or canon in seen:
            continue
        seen.add(canon)
        pop.append(canon)
        if len(pop) >= pop_size:
            break
    return pop
