"""Slice 07-04b: hard structural constraints at the validity gate.

A molecule passes iff it trips NO exclude pattern / catalog alarm AND matches EVERY
required include. Invalid SMILES never pass (never trusted).
"""

from __future__ import annotations

from capychem.constraints import Constraints


def test_smarts_exclude_drops_matching_molecule() -> None:
    c = Constraints.from_json({"smarts_exclude": ["[N+](=O)[O-]"]})  # nitro
    assert c.passes("c1ccccc1") is True  # benzene: no nitro
    assert c.passes("O=[N+]([O-])c1ccccc1") is False  # nitrobenzene excluded


def test_pains_catalog_flags_a_known_alarm() -> None:
    c = Constraints.from_json({"catalogs": ["PAINS", "BRENK"]})
    assert c.passes("c1ccccc1") is True  # benzene is clean
    assert c.passes("Oc1ccc(O)cc1") is False  # hydroquinone is a PAINS/Brenk alarm


def test_smarts_include_requires_the_pattern() -> None:
    c = Constraints.from_json({"smarts_include": ["c1ccccc1"]})  # must contain a benzene ring
    assert c.passes("c1ccccc1CC") is True  # has an aromatic ring
    assert c.passes("CCCC") is False  # aliphatic, no ring -> fails the required include


def test_invalid_smiles_never_passes() -> None:
    c = Constraints.from_json({"smarts_exclude": ["[N+](=O)[O-]"]})
    assert c.passes("not-a-smiles") is False


def test_empty_constraints_pass_everything() -> None:
    c = Constraints.from_json({})
    assert c.passes("c1ccccc1") is True
    assert c.passes("CCCC") is True


# --- constraint-starvation is distinct from plateau / no_progress -------------


def _stop(**over: object) -> str | None:
    from capychem.loop.logic import stop_reason

    base: dict[str, object] = {
        "calls_used": 10, "budget": 100, "gen_index": 3, "max_generations": 100,
        "made_progress": False, "plateau_window": 5,
    }
    base.update(over)
    return stop_reason(**base)  # type: ignore[arg-type]


def test_transient_starvation_does_not_fire_no_progress() -> None:
    # A starved generation (GA keeps proposing) must NOT be read as no_progress —
    # the run keeps trying under the constraints until the starvation window.
    assert _stop(constraint_starved_streak=1) is None


def test_sustained_starvation_terminates_as_constraint_starved() -> None:
    assert _stop(constraint_starved_streak=5) == "constraint_starved"


def test_budget_still_outranks_starvation() -> None:
    assert _stop(calls_used=100, constraint_starved_streak=5) == "exhausted"


def test_no_starvation_keeps_the_normal_no_progress_signal() -> None:
    assert _stop(constraint_starved_streak=0) == "no_progress"
