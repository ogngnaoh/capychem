"""Static Graph-GA AUC-top-10 baseline lookup, keyed by PMO task name.

Loaded once from the G1 full-23 sweep report (docs/04-compare-and-polish/
g1-full23-10k-seed42.json, milestone 04 slice 04) — OUR reproduced same-seed
Graph-GA control, not the published PMO table (packages/core/capychem/eval/
baselines.py holds that; G1's verdicts always compare against our own control, per
its own docstring). Baked in at import time as a static snapshot, not live-refreshed.
None for a task the report doesn't cover (not banked, e.g. sitagliptin_mpo).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPORT_PATH = (
    Path(__file__).resolve().parents[4]
    / "docs"
    / "04-compare-and-polish"
    / "g1-full23-10k-seed42.json"
)


def _load_baselines(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    data: dict[str, Any] = json.loads(path.read_text())
    out: dict[str, float] = {}
    for row in [*data.get("rows", []), *data.get("excluded_rows", [])]:
        out.setdefault(row["task"], row["graph_ga_auc"])
    return out


_BASELINES = _load_baselines(_REPORT_PATH)


def graph_ga_baseline(task: str) -> float | None:
    return _BASELINES.get(task)
