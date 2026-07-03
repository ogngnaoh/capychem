# Slice 06-02 — CI pipeline

**Status:** shipped (frozen)

## Goal
A GitHub Actions CI that runs the full quality gate on the free (no-provider-secret) path, so regressions in the modern code are caught on every push/PR. README CI badge.

## What shipped
- `.github/workflows/ci.yml` — two jobs:
  - **backend**: Postgres 16 service container (creds `capychem/capychem`, `CAPYCHEM_DATABASE_URL` matching `infra/compose.yml`) → `uv sync` → `uv sync --project harness` → `ruff check .` → `mypy -p capychem -p capychem.api` → `pytest -q`.
  - **web**: pnpm 11.5.0 + Node 22 → `pnpm install --frozen-lockfile` → `lint` → `typecheck` → `test`.
- `README.md` — CI status badge linking to the workflow (`ogngnaoh/capychem`).

## Key decisions (verified locally, not assumed)
- **The harness IS built in CI.** The "free stub path" removes LLM keys, but the loop still scores through the PyTDC subprocess oracle. Simulating a harness-less env (`CAPYCHEM_HARNESS_PYTHON=/nonexistent`) made **20 tests fail**, not skip — the loop/API/oracle-bridge tests score `task=qed` (RDKit-computed, no download) and are not fixture-gated. So `uv sync --project harness` is required; harness deps all have Linux/Py3.10 wheels and are lockfile-pinned. Only the 3 `conftest.harness`-gated tests (jnk3, eval-real) touch the network.
- **`ruff format --check` is NOT enforced** — the pre-existing tree predates format enforcement (~29 files would reformat); enforcing it repo-wide is a separate deliberate pass. CI gates `ruff check` (lint), which passes.
- **No axe job yet** — rides in 06-04 after the a11y remediation (06-03), so CI starts green.

## Acceptance — met (locally verified)
- Every CI command run locally on the real repo state: `uv sync` ✓, `uv sync --project harness` ✓ (Python 3.10.20), `ruff check .` ✓, `mypy` ✓ (42 files), `pytest -q` ✓ (**284 passed** with harness), web `lint`/`typecheck` ✓, `test` ✓ (**30 passed**).
- No provider secret referenced anywhere in the workflow.
- Workflow uses only trusted inputs (`github.ref` in a concurrency group, never in a shell `run:`) — no injection surface.

## Notes
- The GitHub-hosted ubuntu run itself is not verifiable without a push (which is an outward action, deferred to the operator). Every command is verified locally as the proxy; the badge will populate once the branch/workflow lands on GitHub.
- The 3 network-touching tests (jnk3 + eval-real) download small ML-oracle models on first CI run; PyTDC's source is stable. If they ever flake, cache the TDC data dir or deselect them — a minor follow-up, not a blocker.
