"""Pure file read of the shipped starting population (no DB, no harness import).

Both the product loop (loop/graph.py) and the headless eval runner
(eval/runner.py) need gen-0 seeds; keeping the read here lets the eval path
import it without pulling in LangGraph / SQLAlchemy.
"""

from __future__ import annotations

from pathlib import Path

# packages/core/capychem/loop/seeds.py -> repo root is parents[4].
_STARTING_POP = (
    Path(__file__).resolve().parents[4]
    / "harness"
    / "capychem_harness"
    / "data"
    / "starting_pop.smi"
)


def load_starting_pop(limit: int) -> list[str]:
    """Return up to ``limit`` SMILES from the shipped starting population file."""
    lines = _STARTING_POP.read_text().splitlines()
    smis = [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    return smis[:limit]
