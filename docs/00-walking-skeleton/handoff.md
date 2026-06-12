# Handoff — 00-walking-skeleton (CLOSED)

## Completed this session

- **Slice 4 (`03-cloudify`) SHIPPED — closes the `00-walking-skeleton` milestone.**
  Implemented via subagent-driven development (per task: fresh implementer + spec-compliance review +
  code-quality review), then a final fresh-context reviewer approved the whole slice. Then the
  milestone-closing Modal cloud gate PASSED end-to-end.
- Commits (branch `slice4-cloudify`, merged to `main`): T1 `f8be08f` · T2 `09a158d` · T3 `2271f47` ·
  T4 `e34cc3b` · T5 `41552af` · T6 `cd20ee9` · ruff format `bab00d7` · docs `c5c289e` + ship docs.
- **Local gate green:** pytest 39, mypy clean, ruff check + format clean, web test 7 / typecheck / lint / build.
- **Cloud gate PASSED:** `modal deploy` published `capychem-worker.score`; `modal run` scored CCO+benzene;
  an end-to-end runner run (`CAPYCHEM_ORACLE_BACKEND=modal`) scored a real QED run via the deployed worker —
  status `exhausted`, 12 oracle calls, top QED 0.94, `RunCost.oracle_cost_usd = 1.1e-5 (> 0)`.

## Slice status across milestone

- `00-foundation` → shipped (2026-05-30)
- `01-local-loop` → shipped (2026-06-11)
- `02-web-surface` → shipped (2026-06-11)
- `03-cloudify` → **shipped (2026-06-12)** — milestone `00-walking-skeleton` complete.

## Current state

- `main` holds the merged slice-4 work and is **pushed to `origin/main`** (`7613f19`). Default `CAPYCHEM_ORACLE_BACKEND=local` keeps CI/dev Modal-free.
- Modal app `capychem-worker` is DEPLOYED (https://modal.com/apps/ogngnaoh/main/deployed/capychem-worker).
- `docs/milestones.md`: `00-walking-skeleton` shipped; `01-harness-reproducibility` ← active.

## Next session start here

Begin milestone **`01-harness-reproducibility`** (SPEC Phase 1): synthesize `docs/01-harness-reproducibility/`
(`milestone.md` + `handoff.md`) when work starts. Goal: pinned harness env reproduces a Graph-GA PMO result;
trivial LangGraph + Langfuse loop spike; >80% valid-SMILES gate.

## Active concerns (carried)

- Modal cost is a placeholder model (`wall_ms × CAPYCHEM_ORACLE_USD_PER_SEC`), dormant-cheap on QED — not a
  price claim (PRD N6). Real cost arrives with the milestone-02 LLM.
- `GET /runs/{id}` DB-read fallback reports `cost_so_far_usd=0.0` even when a `RunCost` row exists (live path
  correct) — milestone-04 follow-up.
- Langfuse trace still unverified end-to-end (no keys; no-op path runs). `Run.ended_at` unset; post-restart
  snapshots read in-memory; top-10 sort key triplicated.

## Slice log

- 2026-06-12 — Slice 4 (`03-cloudify`) SHIPPED; cloud gate passed (deployed Modal worker scored a run, RunCost>0); milestone `00-walking-skeleton` closed.
- 2026-06-11 — Slice 4 planned + reviewed (spec/plan/slice doc).
- 2026-06-11 — Slice 3 (`02-web-surface`) shipped.
- 2026-06-11 — Slice 2 (`01-local-loop`) shipped.
- 2026-05-30 — Slice 1 (`00-foundation`) shipped.
