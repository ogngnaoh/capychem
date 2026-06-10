from __future__ import annotations

from capychem.validate import ValidCandidate, canonicalize, validate_batch


def test_canonicalize_returns_canonical_form() -> None:
    # Two spellings of ethanol canonicalize to the same string.
    assert canonicalize("OCC") == canonicalize("CCO")


def test_canonicalize_returns_none_for_invalid() -> None:
    assert canonicalize("not_a_smiles") is None


def test_validate_batch_drops_invalid_and_dedups_keeping_first_provenance() -> None:
    batch = [
        ("CCO", (0, 1)),
        ("OCC", (2, 3)),          # duplicate of CCO by canonical form
        ("not_a_smiles", (4, 5)), # invalid -> dropped
        ("c1ccccc1", None),       # gen-0 style, no parents
    ]
    out: list[ValidCandidate] = validate_batch(batch)
    assert [c.smiles for c in out] == [canonicalize("CCO"), canonicalize("c1ccccc1")]
    assert out[0].parents == (0, 1)  # first occurrence wins
    assert out[1].parents is None


def test_validate_batch_empty_on_all_invalid() -> None:
    assert validate_batch([("xxx", None), ("yyy", None)]) == []
