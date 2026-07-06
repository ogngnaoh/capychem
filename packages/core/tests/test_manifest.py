"""Slice 07-06: provenance manifest (OD-5) — harness emits its PyTDC version, and a
run's manifest cites the real model id + PyTDC pin + git SHA.
"""

from __future__ import annotations

from capychem.oracle import pytdc_version
from capychem.run import RunConfig, build_manifest


def test_harness_emits_its_pytdc_version() -> None:
    # Goes through the isolated harness subprocess; proves score.py now emits the field
    # and oracle.pytdc_version parses it. The pinned legacy env is PyTDC 0.3.6.
    assert pytdc_version() == "0.3.6"


def test_build_manifest_carries_provenance() -> None:
    cfg = RunConfig(
        task="qed", budget=100, seed=42, pop_size=10, offspring=4,
        mutation_rate=0.01, plateau_window=5, max_generations=10, mode="benchmark",
    )
    m = build_manifest(
        cfg,
        git_sha="abc1234",
        model_id="deepseek-v4-pro",
        pytdc_version="0.3.6",
        trace_url="http://langfuse/trace/1",
    )
    assert m["git_sha"] == "abc1234"
    assert m["model_id"] == "deepseek-v4-pro"
    assert m["pytdc_version"] == "0.3.6"
    assert m["trace_url"] == "http://langfuse/trace/1"
    assert m["config"]["task"] == "qed"
    assert m["config"]["budget"] == 100
    assert m["config"]["mode"] == "benchmark"
