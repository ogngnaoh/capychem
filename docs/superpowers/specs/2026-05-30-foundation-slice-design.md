# Design — Walking Skeleton Slice 1: `00-foundation`

**Date:** 2026-05-30
**Milestone:** `00-walking-skeleton`
**Status:** Approved & implemented

## Context

The walking-skeleton milestone front-loads integration risk: ship a thin end-to-end
slice that exercises every seam before SPEC §9's rigor phases. Slice 1 is the scaffold
the rest of the skeleton stands on. The repo was greenfield (only `docs/` existed).

The one load-bearing seam is the **harness↔modern boundary**: the legacy PMO eval
stack (`mol_opt` + PyTDC 0.3.6, Python 3.10) must stay isolated from modern Python 3.12
code and be reached only via a subprocess + JSON bridge — never `import`. Proving a
*real* QED oracle score flows across that bridge is this slice's headline outcome.

## Decisions

- **Harness env uses `uv`, not conda.** Overrode the original docs (CLAUDE.md / SPEC.md /
  PROJECT.md all said "conda env `capychem-harness`"). The harness is a *separate* uv
  project (`harness/pyproject.toml`, own lockfile, `package = false`) pinned to Python
  3.10 and **excluded from the root workspace**, so its ancient deps never resolve against
  the 3.12 lockfile. Isolation is physically enforced by a distinct interpreter at
  `harness/.venv/bin/python`.
- **Bridge bar = a real QED score end-to-end**, not a stub.
- **Postgres + Langfuse containers stood up now** (colima runtime), connectivity-checked
  only — no schema, no spans yet (those land in slice 2).
- **Hello-world web page fetches the API `/healthz`**, exercising CORS early.
- **Single slice** as the milestone defines it.

## Architecture

```
apps/web/    Next.js 16 + React 19 + TS + Tailwind — page fetches API /healthz (client-side)
apps/api/    FastAPI /healthz, CORS locked to http://localhost:3000   (capychem.api namespace)
packages/core/capychem/oracle.py   subprocess bridge client            (capychem namespace)
harness/     ISOLATED uv project (py3.10, PyTDC 0.3.6, rdkit) — NOT a workspace member
  capychem_harness/score.py        stdin JSON → tdc.Oracle → stdout JSON
infra/compose.yml                  Postgres 16
infra/langfuse-compose.yml         Langfuse v2 (single-Postgres footprint)
scripts/smoke.sh                   the slice exit gate
```

`capychem` is a **PEP 420 namespace package** split across two distributions
(`capychem-core` → `capychem.oracle`, `capychem-api` → `capychem.api`). No
`capychem/__init__.py` anywhere — that is what lets the two merge. uv workspace members
are `packages/core` + `apps/api`; `harness/` is deliberately excluded.

## The bridge contract (load-bearing)

- Request (stdin): `{"task": "qed", "smiles": ["c1ccccc1", ...]}`
- Response (stdout): `{"task": "qed", "results": [{"smiles", "score", "valid", "wall_ms"}], "error": null}`
- Modern side `score_smiles()` shells out to `harness/.venv/bin/python` (override via
  `CAPYCHEM_HARNESS_PYTHON`), parses the last JSON line, raises `HarnessError` on failure.
- Harness side redirects library chatter to stderr so only JSON reaches stdout; marks
  `valid` via RDKit; scores via PyTDC.

## Install hazards surfaced (and resolved)

PyTDC 0.3.6 has incomplete dependency metadata and assumes an ancient RDKit:
1. It imports `requests`, `networkx` (and needs `scipy`) without declaring them → added
   explicitly to the harness deps.
2. It does `from rdkit.six import iteritems`, but modern RDKit removed `rdkit.six` → the
   scorer injects a one-symbol `rdkit.six` shim before importing `tdc` (PyTDC uses it in
   exactly one place). Keeps modern RDKit (clean arm64 wheel) instead of pinning an old one.

This is precisely the "legacy dependency surface" risk the SPEC flagged, surfaced and
neutralized on day one — the point of the walking skeleton.

## Deferred (not this slice)

- DB schema + Langfuse spans → slice 2.
- `mol_opt` / Graph-GA proposer → slice 2 (only the QED oracle is needed here).
- Modal-hosted oracle → slice 4.
- shadcn/ui, web test (vitest) + format (prettier) harness → slice 3.
- Docker fallback for the harness (`linux/amd64` image) was the documented escape hatch;
  not needed — the native uv install worked.

## Verification

`scripts/smoke.sh` is the gate: harness venv present → QED bridge pytest (real score) →
ruff → mypy strict → web typecheck + lint → Postgres `pg_isready` → Langfuse health.
Result: **8/8 passed**. Benzene QED = 0.4426 through the subprocess bridge.
