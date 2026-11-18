"""Run mode: the benchmark/exploratory invariant.

Every run carries a ``mode``. Only ``benchmark`` runs feed the committed G1
numbers; the moment a run uses ANY custom input — an
operator seed population, a pluggable/composed objective, or a constraint set —
it is ``exploratory`` and is never presented as benchmark-comparable.

``derive_mode`` is the one place that decision is made. Mode is server-derived
from the run's inputs, never accepted from the client, so a run cannot claim a
benchmark tag it hasn't earned. All custom seed, objective and constraint inputs
pass through this function.
"""

from __future__ import annotations

from typing import Any, Literal

Mode = Literal["benchmark", "exploratory"]


def derive_mode(
    *,
    objective_json: dict[str, Any] | None = None,
    constraints_json: dict[str, Any] | None = None,
    seed_smiles: list[str] | None = None,
) -> Mode:
    """Return ``"exploratory"`` if any custom input is present, else ``"benchmark"``.

    Presence is truthiness: ``None``, ``[]``, and ``{}`` all read as "no custom
    input" so a client posting an empty seed list or empty objective does not
    silently drop the run out of the benchmark denominator.
    """
    if seed_smiles or objective_json or constraints_json:
        return "exploratory"
    return "benchmark"
