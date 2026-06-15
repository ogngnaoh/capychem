"""The single authoritative AUC-of-top-10 metric.

Faithful port of PMO ``main/optimizer.py::top_auc`` (see
agent_docs/pmo-auc-and-baselines.md for the verbatim source). This is the
canonical G1 number; the running curve in loop/logic.py is a live-UI estimate
only -- do not let a second AUC definition drift in.
"""

from __future__ import annotations


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def top_auc(
    buffer: dict[str, tuple[float, int]],
    top_n: int = 10,
    finish: bool = True,
    freq_log: int = 100,
    max_oracle_calls: int = 10000,
) -> float:
    """Trapezoidal AUC of the running-best top-``top_n`` mean vs unique oracle calls.

    ``buffer`` maps canonical SMILES -> (score, call_order), where call_order is
    the 1-based ordinal at which the SMILES was first scored. Returns a value in
    [0, 1] because PMO oracle scores live in [0, 1].
    """
    total = 0.0
    prev = 0.0
    called = 0
    ordered = sorted(buffer.items(), key=lambda kv: kv[1][1])  # chronological replay
    for idx in range(freq_log, min(len(buffer), max_oracle_calls), freq_log):
        window = sorted(ordered[:idx], key=lambda kv: kv[1][0], reverse=True)[:top_n]
        top_now = _mean([item[1][0] for item in window])
        total += freq_log * (top_now + prev) / 2
        prev = top_now
        called = idx
    tail = sorted(ordered, key=lambda kv: kv[1][0], reverse=True)[:top_n]
    top_now = _mean([item[1][0] for item in tail])
    total += (len(buffer) - called) * (top_now + prev) / 2
    if finish and len(buffer) < max_oracle_calls:
        total += (max_oracle_calls - len(buffer)) * top_now
    return total / max_oracle_calls
