"""Slice 07-05: per-candidate molecule-quality report (reward-hacking defense)."""

from __future__ import annotations

from capychem.quality import molecule_quality

_QUALITY_KEYS = {
    "valid", "sa_score", "qed", "mw", "logp", "hbd", "hba",
    "rotatable_bonds", "tpsa", "lipinski_pass", "veber_pass", "pains", "brenk",
}


def test_caffeine_is_a_clean_drug_like_molecule() -> None:
    q = molecule_quality("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")
    assert q["valid"] is True
    assert set(q) == _QUALITY_KEYS
    assert q["lipinski_pass"] is True
    assert q["veber_pass"] is True
    assert q["pains"] is False and q["brenk"] is False  # no structural alarm
    assert 0.0 <= q["qed"] <= 1.0 and q["sa_score"] > 0


def test_hydroquinone_trips_a_structural_alarm() -> None:
    q = molecule_quality("Oc1ccc(O)cc1")
    assert q["valid"] is True
    assert q["pains"] is True or q["brenk"] is True  # a known structural alarm (Brenk)


def test_invalid_smiles_reports_not_valid() -> None:
    q = molecule_quality("not-a-smiles")
    assert q["valid"] is False


def test_lipinski_fails_for_a_heavy_greasy_molecule() -> None:
    # A long alkane chain: high MW + logP, many rotatable bonds -> fails Ro5 + Veber.
    q = molecule_quality("C" * 60)
    assert q["valid"] is True
    assert q["lipinski_pass"] is False
    assert q["veber_pass"] is False  # > 10 rotatable bonds


# --- run-level diversity + novelty in build_summary ---------------------------


def test_summary_diversity_and_novelty() -> None:
    from capychem.loop.logic import build_summary
    from capychem.loop.state import Scored

    identical = build_summary(
        [Scored("CCO", 0.5), Scored("CCO", 0.5)], [], generations=1, oracle_calls=2
    )
    assert identical["diversity"] == 0.0  # identical molecules -> zero internal diversity

    distinct = build_summary(
        [Scored("CCO", 0.5), Scored("c1ccccc1", 0.4)],
        [],
        generations=1,
        oracle_calls=2,
        seed_pop={"CCO"},
    )
    assert distinct["diversity"] > 0.0
    assert distinct["novelty"] == 0.5  # benzene is novel, ethanol was in the seed
