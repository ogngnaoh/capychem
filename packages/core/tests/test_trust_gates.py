"""Slice 07-05: the shared trust-gate home — one PARSE_RATE_FLOOR, plus a
custom-oracle canary that flags an oracle scoring degenerate probes implausibly high.
"""

from __future__ import annotations

from capychem.trust.gates import PARSE_RATE_FLOOR, oracle_canary


def test_parse_rate_floor_is_the_single_source() -> None:
    # eval.beat and eval.verdict must consume THIS constant, not their own copies.
    from capychem.eval import beat, verdict

    assert PARSE_RATE_FLOOR == 0.8
    assert beat._PARSE_RATE_FLOOR is PARSE_RATE_FLOOR
    assert verdict._PARSE_RATE_FLOOR is PARSE_RATE_FLOOR


class _DegenerateOracle:
    """Scores every molecule 1.0 — the reward-hacking tell a canary must catch."""

    name = "degenerate"
    version = "test"
    direction = "maximize"

    def score(self, smiles: list[str]) -> list[float | None]:
        return [1.0 for _ in smiles]


class _SaneOracle:
    name = "sane"
    version = "test"
    direction = "maximize"

    def score(self, smiles: list[str]) -> list[float | None]:
        return [0.05 for _ in smiles]


def test_canary_flags_a_degenerate_oracle() -> None:
    result = oracle_canary(_DegenerateOracle())
    assert result.suspicious is True
    assert result.max_score == 1.0


def test_canary_passes_a_sane_oracle() -> None:
    result = oracle_canary(_SaneOracle())
    assert result.suspicious is False
