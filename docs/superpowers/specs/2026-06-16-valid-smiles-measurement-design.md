# Design — Valid-SMILES Measurement (CapyChem slice `03-valid-smiles-measurement`)

**Date:** 2026-06-16
**Milestone:** 01-harness-reproducibility (final slice)
**Status:** Approved (brainstorm), pre-plan

## Problem

Milestone 01 must prove the measurement plumbing for a per-run valid-SMILES rate
exists and works, exercised against the deterministic Graph-GA proposer. The
**>80% pass/fail gate check is explicitly milestone 02** (it rides with the LLM
proposer). Slice 3 measures only; it must produce a *stable* per-run field that
the milestone-02 gate later compares against >80%.

## Key design decision — parse-validity, not dedup

`validate.py::validate_batch()` does two things in one pass: it drops
un-parseable SMILES **and** collapses intra-batch duplicate molecules. A repeated
molecule is still chemically valid, so `len(proposed) − len(validated)` conflates
"invalid" with "duplicate".

**Decision (user-approved):** the valid-SMILES rate is **parse-validity only** —
`rate = (RDKit-parseable SMILES) / (SMILES proposed)`. Duplicates count as valid.
This is exactly what the milestone-02 gate means by "valid-SMILES rate from the
LLM": it measures one thing (can RDKit parse it), not validity-and-novelty.

## Approved scope decisions

| Decision | Choice | Why |
|---|---|---|
| Rate semantics | Parse-validity only (dupes count as valid) | Matches milestone-02 gate meaning |
| Storage | `summary_json` (no DB migration) | Mirrors `auc_curve`/`top_k`; existing `GET /runs/{id}` returns it |
| Granularity | Per-run cumulative rate + raw counts | The deliverable + exact gate input; auditable |
| Surfacing | Measurement-only / headless (summary_json + CLI) | Milestone 01 is headless; no API/web (that's milestone 04) |

No escalation: no schema migration, no API/web changes → small additive in-session slice.

## Design

**1. `packages/core/capychem/validate.py` — add a stats seam.**
Keep `validate_batch` behavior identical; add a stats-returning sibling so the
parse-valid count is captured *before* dedup.

```python
@dataclass(frozen=True)
class ValidationStats:
    proposed: int
    valid: int            # RDKit-parseable, counted BEFORE dedup
    @property
    def rate(self) -> float:
        return self.valid / self.proposed if self.proposed else 0.0

def validate_batch_with_stats(
    candidates: list[tuple[str, tuple[int, int] | None]],
) -> tuple[list[ValidCandidate], ValidationStats]:
    seen: set[str] = set()
    out: list[ValidCandidate] = []
    valid = 0
    for raw, parents in candidates:
        canon = canonicalize(raw)
        if canon is None:
            continue
        valid += 1                  # parse-valid, before dedup
        if canon in seen:
            continue
        seen.add(canon)
        out.append(ValidCandidate(smiles=canon, parents=parents))
    return out, ValidationStats(proposed=len(candidates), valid=valid)

def validate_batch(candidates):     # unchanged public behavior
    out, _ = validate_batch_with_stats(candidates)
    return out
```

**2. `packages/core/capychem/loop/state.py` — one transient accumulator.**
Add `_validation_stats: dict[str, int]` (`{"proposed", "valid"}`), underscore-prefixed
transient, mirroring the `auc_curve` accumulation idiom.

**3. `packages/core/capychem/loop/graph.py` — accumulate in the `validate` node.**
Switch to `validate_batch_with_stats`; read prior `_validation_stats` via
`state.get(..., {"proposed": 0, "valid": 0})`, add this batch's counts, write back.
Same cross-generation merge pattern `auc_curve` already uses.

**4. `packages/core/capychem/loop/logic.py` — `build_summary()` emits the field.**
New optional `validation_stats` kwarg; when present, add a stable block:
```python
summary["valid_smiles"] = {"proposed": P, "valid": V, "rate": V / P if P else 0.0}
```
`stop_check` passes `state.get("_validation_stats")` through. This is the exact,
stable field the milestone-02 gate reads.

**5. `packages/core/capychem/cli.py` — print the rate** at run end (headless surface).
`GET /runs/{id}` already returns `summary_json`, so the API surface is free.

## Testing

TDD in-session (RED→GREEN→REFACTOR):
- `test_validate.py`: `validate_batch_with_stats` — duplicates count as valid;
  invalid drop from both list and count; `rate` math; empty-batch rate = 0.0.
- `test_loop_logic.py`: `build_summary` with stats → includes `valid_smiles`
  block with correct rate; without stats → omits the block.

Verification: `uv run pytest` · `uv run mypy -p capychem -p capychem.api` ·
`uv run ruff check .`. Then a real Graph-GA QED run; record the measured per-run
rate as evidence (expect ~100% — deterministic graph edits; the plumbing is the
deliverable, not the number).

## Out of scope (deferred)

- The >80% valid-SMILES **gate check** → milestone 02 (rides with the LLM proposer).
- LLM proposer → milestone 02.
- Per-generation rate series → not needed (Graph-GA rate is ~flat at ~100%).
- API response field / web run-detail surface → milestone 04.
- Seed-population exclusion from the rate → not needed; measure whatever flows
  through `validate`.
- Product-loop memoization / unique-call budget → milestone 02. Do not touch `eval/`.
