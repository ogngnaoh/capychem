from __future__ import annotations

from capychem.validate import (
    ValidCandidate,
    ValidationStats,
    canonicalize,
    validate_batch,
    validate_batch_with_stats,
)


def test_canonicalize_returns_canonical_form() -> None:
    # Two spellings of ethanol canonicalize to the same string.
    assert canonicalize("OCC") == canonicalize("CCO")


def test_canonicalize_returns_none_for_invalid() -> None:
    assert canonicalize("not_a_smiles") is None


def test_validate_batch_drops_invalid_and_dedups_keeping_first_provenance() -> None:
    batch = [
        ("CCO", (0, 1)),
        ("OCC", (2, 3)),  # duplicate of CCO by canonical form
        ("not_a_smiles", (4, 5)),  # invalid -> dropped
        ("c1ccccc1", None),  # gen-0 style, no parents
    ]
    out: list[ValidCandidate] = validate_batch(batch)
    assert [c.smiles for c in out] == [canonicalize("CCO"), canonicalize("c1ccccc1")]
    assert out[0].parents == (0, 1)  # first occurrence wins
    assert out[1].parents is None


def test_validate_batch_empty_on_all_invalid() -> None:
    assert validate_batch([("xxx", None), ("yyy", None)]) == []


def test_validate_batch_with_stats_counts_parse_validity_before_dedup() -> None:
    batch = [
        ("CCO", (0, 1)),
        ("OCC", (2, 3)),  # duplicate of CCO by canonical form — still parse-valid
        ("not_a_smiles", None),  # invalid — not counted as valid
        ("c1ccccc1", None),
    ]
    out, stats = validate_batch_with_stats(batch)
    # dedup still applies to the returned list (unchanged validate_batch behavior)
    assert [c.smiles for c in out] == [canonicalize("CCO"), canonicalize("c1ccccc1")]
    # but the duplicate counts as VALID: 3 parseable of 4 proposed
    assert stats.proposed == 4
    assert stats.valid == 3
    assert stats.rate == 0.75


def test_validation_stats_rate_zero_on_empty_batch() -> None:
    out, stats = validate_batch_with_stats([])
    assert out == []
    assert stats.proposed == 0 and stats.valid == 0
    assert stats.rate == 0.0  # no division-by-zero


def test_validate_batch_with_stats_all_invalid() -> None:
    out, stats = validate_batch_with_stats([("xxx", None), ("yyy", None)])
    assert out == []
    assert stats.proposed == 2 and stats.valid == 0
    assert stats.rate == 0.0
