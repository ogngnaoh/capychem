# Milestone 06 — production-hardening

**Goal:** Bring the shipped CapyChem engine to production-grade polish — honest fork-and-run docs, CI-gated quality, WCAG-AA accessibility, safe migrations, and cheap reliability — without adding any new product feature or reopening the frozen benchmark path.

## Scope
- Repo hygiene + honest fork-and-run docs: LICENSE (MIT), CONTRIBUTING, real `apps/web/README.md`, complete `.env.example`, root README reframe preserving G1 honesty.
- Env-driven `ALLOWED_ORIGINS` (one source, CORS + WS).
- Cost-gate reconciliation: SPEC §8.3 text → the shipped flat env-tunable `$50` cap; a guard test.
- CI: GitHub Actions running backend (pytest/mypy/ruff) + web (lint/typecheck/test) on the free stub/graph_ga path; README badge.
- Accessibility remediation to WCAG AA at the 1280px target: primary-button contrast, focus ring, live-run `aria-live`, `role="alert"`, fetch-error surfacing, skip link, per-route titles, `aria-sort`, concise molecule alt.
- axe-core CI gate across 5 routes in light+dark (rides after a11y fixes so CI starts green).
- Alembic baseline (enabling gate for milestone 07): initial revision = current schema; retire drop-recreate.
- Cheap reliability (OD-1): recoverable `paused` status on `HarnessError`, oracle-path transient tolerance, in-process durable resume rebuilt from Postgres rows, startup sweep → paused+resume, Modal `propose` n>1 + transient parity.

## Non-goals
- **No new product features** — no pluggable oracle, no objective composition, no seed-import, no quality layer (all milestone 07).
- **No benchmark-path change** — the frozen G1 path is touched only for read-only surfacing; benchmark numbers must reproduce unchanged.
- **No auth / hosting / multi-user** (NG-1/NG-2; pivot dropped these consciously).
- **No durable-Modal-loop** — OD-1 chose the cheap in-process resume, not a durable job runner.
- **No schema columns beyond what Alembic needs** — new feature columns land in milestone 07 through Alembic revisions.
- **No real-world efficacy claims** (N6) — every score stays in-silico-labeled.

## Slices (execution order)
1. `06-01-repo-hygiene-and-docs` — LICENSE, CONTRIBUTING, web README, .env.example, env-driven origins, cost-gate doc reconciliation. — shipped
2. `06-02-ci-pipeline` — `.github/workflows/ci.yml` (backend + web, builds harness) + README badge. — shipped
3. `06-03-a11y-remediation` — contrast/focus/aria-live/errors/skip-link/titles/aria-sort/alt + dl/scrollable/coral-demotion. — shipped
4. `06-04-axe-ci-gate` — Playwright + axe-core across 5 routes, light+dark (10/10 green); added to CI. — shipped
5. `06-05-alembic-baseline` — initial revision = current schema; adopt-or-upgrade startup wiring; retire drop-recreate. — shipped
6. `06-06-reliability-patches` — pause + durable resume + oracle-fault tolerance + Modal n>1. — planned

## Integration notes
- **Ordering:** 06-01→06-04 touch no schema and reopen nothing → ship first. 06-05 (Alembic) is the enabling gate that unblocks every milestone-07 column. 06-06 needs no new column (`paused` fits `String(16)`; resume reconstructs from existing rows) so it can land independently of Alembic.
- **CI vs a11y:** the axe gate (06-04) must land *after* the a11y fixes (06-03) or the first CI run fails; 06-02 starts green with backend+web-lint/type/test only.
- **Cost-gate:** keep `cost.py:16` flat cap as-is; the slice only reconciles the SPEC §8.3 prose and adds a documents-the-behavior guard test. No projective check.
- **Touchpoints by path:** docs/hygiene → `LICENSE`,`CONTRIBUTING.md`,`README.md`,`apps/web/README.md`,`.env.example`; origins → `apps/api/capychem/api/config.py`(+`main.py`,`ws_runs.py`); cost → `SPEC.md`,`packages/core/capychem/cost.py`,`packages/core/tests/test_cost_gate.py`; CI → `.github/workflows/ci.yml`; a11y → `apps/web/app/globals.css`,`components/ui/button.tsx`,`components/workbench/{AppShell,ui}.tsx`,`app/runs/[id]/{LiveRun,Cockpit}.tsx`,`app/{Overview,launch/Launcher,compare/CompareView,runs/RunsBrowse}.tsx`,5 `page.tsx` route files; Alembic → `alembic.ini`,`packages/core/capychem/db/migrations/`,`db/session.py`; reliability → `apps/api/capychem/api/{runner,main}.py`,`packages/core/capychem/{loop/graph.py,resume.py}`,`apps/worker/app.py`,`proposer.py`.

## Exit criteria
- `LICENSE` + `CONTRIBUTING.md` tracked; `apps/web/README.md` is a real app README; root README carries the fork-and-run framing with every G1 honesty caveat intact (no "21/23" anywhere).
- `ALLOWED_ORIGINS` drives both CORS and the WS origin check from one env-parsed source; a test proves it.
- CI is green on a clean checkout (backend + web + axe), no provider secrets required.
- axe-core reports zero serious/critical violations across the 5 routes in both themes; primary button ≥4.5:1, focus ring ≥3:1; a completed generation is announced to screen readers.
- `alembic upgrade head` builds the current schema on a fresh DB and is a safe no-op (via stamp) on an existing `create_all` DB; `uv run pytest` passes against the migrated schema.
- A `HarnessError` mid-run yields a `paused`, resumable run with a browseable partial summary; a resume continues to the same terminal state a crash-free run would reach (G6-safe); worker `propose(n>1)` returns n distinct candidates and degrades a 429 gracefully.
