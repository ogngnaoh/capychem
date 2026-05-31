# Slice 1 — `00-foundation`

**Milestone:** `00-walking-skeleton` · **Status:** shipped (2026-05-30)

## Goal

Stand up the CapyChem monorepo and prove the load-bearing harness↔modern seam: a real
QED oracle score crosses the subprocess + JSON bridge, with hello-world web + API and the
Postgres + Langfuse containers reachable.

## Plan

- Monorepo: uv workspace (Python 3.12; members `packages/core`, `apps/api`) + pnpm
  workspace (`apps/web`). `harness/` is an isolated uv project (Python 3.10), **not** a
  workspace member.
- Harness bridge: `harness/capychem_harness/score.py` (stdin JSON → PyTDC oracle → stdout
  JSON), called from `packages/core/capychem/oracle.py::score_smiles` via subprocess.
- API: FastAPI `/healthz` with CORS locked to `localhost:3000`.
- Web: Next.js page fetching `${NEXT_PUBLIC_API_URL}/healthz`.
- Infra: `infra/compose.yml` (Postgres 16) + `infra/langfuse-compose.yml` (Langfuse v2).
- Gate: `scripts/smoke.sh`.

## Tasks

- [x] Isolated harness uv env (py3.10, PyTDC 0.3.6, rdkit, +undeclared deps) + `score.py`
- [x] Resolve PyTDC install hazards (missing `requests`/`networkx`/`scipy`; `rdkit.six` shim)
- [x] Validate real QED score through the bridge (benzene = 0.4426; invalid SMILES handled)
- [x] uv workspace roots + pnpm workspace + `.gitignore`/`.env.example`/`.python-version`
- [x] `packages/core` bridge client `score_smiles` + `OracleResult` + `HarnessError`
- [x] Bridge pytest (`test_qed_benzene`, `test_invalid_smiles_is_marked_not_valid`)
- [x] PEP 420 namespace package wired (mypy `-p capychem`, strict, green)
- [x] FastAPI `/healthz` + CORS (verified `access-control-allow-origin: localhost:3000`)
- [x] Next.js 16 app; page fetches `/healthz`; typecheck + lint + production build green
- [x] Tooling: pnpm (brew) + colima/docker + `docker compose` plugin wiring
- [x] Postgres + Langfuse containers up; connectivity verified
- [x] `scripts/smoke.sh` exit gate — **8/8 passing**
- [x] Correct conda→uv (and Next 15→16, Python pin) across the four docs

## Notes

- **Deviation from original docs:** harness uses `uv`, not conda (CLAUDE.md/SPEC/PROJECT
  corrected). Also Next.js 16 (not 15 — create-next-app@latest), Python pinned to 3.12.
- **PyTDC 0.3.6 hazards** (resolved): undeclared `requests`/`networkx`/`scipy`; and
  `from rdkit.six import iteritems` against modern RDKit, fixed with a one-symbol shim in
  `score.py`. The Docker-harness fallback was not needed.
- **Deferred to later slices:** DB schema + Langfuse spans (slice 2); `mol_opt`/Graph-GA
  proposer (slice 2); Modal oracle (slice 4); shadcn/ui + web test/format harness (slice 3).
- Infra containers were left running; `docker compose -f infra/compose.yml -f infra/langfuse-compose.yml down` to stop (note: two separate `-f` invocations, one per file).
- Live browser render of the health page is the one manual check (start API + `pnpm --filter web dev`, open `localhost:3000`).
