# Handoff — 00-walking-skeleton

## Completed this session

- **Slice 4 (`03-cloudify`) IMPLEMENTED + fully reviewed + locally green — NOT yet shipped (Modal cloud gate pending).**
  Executed via subagent-driven development: per task a fresh implementer + a spec-compliance review + a
  code-quality review; then a final fresh-context reviewer approved the whole slice (verdict: ready to
  merge, cloud gate correctly pending; no Critical/Important issues). All commits on branch `slice4-cloudify`.
- Commits: T1 `RunCost`+`capychem.cost` `f8be08f` · T2 `OracleResult.cost_usd`+env-backend `09a158d` ·
  T3 thread cost / async score node `2271f47` · T4 cost gate + `cost_capped` + `cost_so_far_usd` events
  `e34cc3b` · T5 Modal worker + `modal` dep (CODE only) `41552af` · T6 live-view cost counter + badge
  `cd20ee9` · ruff format `bab00d7`.
- **Local gate GREEN:** pytest 39, mypy clean, ruff check + format clean, web test 7 / typecheck / lint /
  build. Harness-backed tests use `CAPYCHEM_HARNESS_PYTHON` → main checkout's `harness/.venv`; Postgres up.

## Slice status across milestone

- `00-foundation` → shipped (2026-05-30)
- `01-local-loop` → shipped (2026-06-11)
- `02-web-surface` → shipped (2026-06-11)
- `03-cloudify` → **implemented + reviewed + locally green on branch `slice4-cloudify`; NOT shipped — Modal cloud gate pending**

## Current state

- Branch `slice4-cloudify` (not merged to `main`, not pushed). Default `CAPYCHEM_ORACLE_BACKEND=local`
  keeps everything Modal-free and green. Modal worker CODE statically verified against installed modal 1.5.0;
  NO cloud deploy/run performed — no `MODAL_TOKEN_*` in this environment.

## Next session start here — close the slice + milestone (needs a Modal account)

1. `modal setup` (writes `MODAL_TOKEN_*`); export the same tokens into the API process env.
2. From repo ROOT (worker `add_local_dir` is cwd-relative): `modal deploy apps/worker/app.py`.
3. `export CAPYCHEM_ORACLE_BACKEND=modal CAPYCHEM_ORACLE_USD_PER_SEC=0.00004`; run API + web; launch a small
   browser QED run → confirm scoring via the deployed worker, live cost counter rises, `RunCost.oracle_cost_usd > 0`,
   Langfuse trace intact.
4. Ship: merge `slice4-cloudify` → `main`, then the ship ritual — flip `03-cloudify`→shipped in `milestone.md`
   + this handoff; freeze `03-cloudify.md`; add a "Slice 4 shipped" log line; mark `00-walking-skeleton`
   shipped + milestone `01` ← active in `docs/milestones.md`.

## Active concerns

- Cloud-gate risks (final review): run `modal deploy` from repo root; tokens in the API env; flip backend +
  set a non-zero rate or cost stays 0; first call cold-start + PyTDC data fetch (240s/300s timeouts give headroom);
  the unchanged `rdkit.six` shim runs in-container at exec — validated by the first cloud smoke.
- `GET /runs/{id}` DB-read fallback reports `cost_so_far_usd=0.0` even when a `RunCost` row exists (live path
  correct) — documented milestone-04 follow-up.
- Carried: `Run.ended_at` unset; post-restart snapshots read in-memory; top-10 sort key triplicated.

## Slice log

- 2026-06-12 — Slice 4 (`03-cloudify`) implemented + fully reviewed + locally green (branch `slice4-cloudify`); ship pending Modal cloud gate.
- 2026-06-11 — Slice 4 (`03-cloudify`) planned + reviewed (spec/plan/slice doc).
- 2026-06-11 — Slice 3 (`02-web-surface`) shipped.
- 2026-06-11 — Slice 2 (`01-local-loop`) shipped.
- 2026-05-30 — Slice 1 (`00-foundation`) shipped.
