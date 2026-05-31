# Handoff — 00-walking-skeleton

## Completed this session

- **2026-05-30 — Slice 1 `00-foundation` shipped** (this session's single slice commit on
  `main`; hash in `git log`). Walking-skeleton scaffold + the load-bearing harness↔modern
  subprocess bridge, proven with a real QED score.
- Design spec: `docs/superpowers/specs/2026-05-30-foundation-slice-design.md`.
- Slice doc `docs/00-walking-skeleton/00-foundation.md` (frozen).
- Corrected conda→uv (also Next 15→16, Python pin, mypy `-p capychem`) across CLAUDE.md,
  SPEC.md, PROJECT.md, milestone.md.

## Slice status across milestone

- `00-foundation` → shipped
- `01-local-loop` → planned (next)
- `02-web-surface` → planned
- `03-cloudify` → planned

## Current state

- Branch `main`. Monorepo live: uv workspace (`packages/core`, `apps/api`, py3.12) + pnpm
  workspace (`apps/web`, Next 16). Isolated harness uv env at `harness/.venv` (py3.10).
- `scripts/smoke.sh` → **8/8 passing** (harness QED bridge, ruff, mypy strict, web
  typecheck/lint, Postgres `pg_isready`, Langfuse health).
- Infra containers left **running** (colima): `capychem-postgres`, `capychem-langfuse`,
  `capychem-langfuse-db`. Stop with `docker compose -f infra/compose.yml down` and
  `docker compose -f infra/langfuse-compose.yml down`.
- Bridge proven: benzene QED = 0.4426 via subprocess; invalid SMILES handled gracefully.

## Next session start here

Open slice 2 (`01-local-loop`). Author `docs/00-walking-skeleton/01-local-loop.md`, then
build the LangGraph propose→validate→score→persist loop with the Graph-GA proposer. This
requires installing `mol_opt` into the harness env (`harness/`), introducing the Postgres
schema (Run/Generation/Candidate/OracleCall), and a CLI that runs QED end-to-end locally.

## Active concerns

- `mol_opt` is NOT yet installed in the harness (only PyTDC for QED). Slice 2 must add it —
  expect more legacy-dep friction (old PyTorch pins); the `rdkit.six` shim pattern is the
  precedent. Docker-harness fallback remains the escape hatch if a native install fails.
- Langfuse v2 (single Postgres) is up but unused; slice 2 wires the first spans. v3's
  Clickhouse/Redis/Minio stack was deliberately avoided for the skeleton.
- Live browser render of the health page is the one step verified only by its parts (API
  CORS + web build), not an automated browser test.
