# Handoff — milestone 07 objective-ownership → **COMPLETE (2026-07-06)**

## Next session start here (milestone boundary — start milestone 08 FRESH)
Milestone 07 is **fully shipped** (all 8 slices; backend + UI). Per the milestone-boundary
convention, do NOT continue milestone 08 in this session's thread — **start milestone 08 in a
fresh session.** First action there:
1. Read `docs/milestones.md`, then decide/synthesize milestone 08's scope from the plan
   `docs/superpowers/plans/2026-07-03-capychem-production-v1.md` (the reliable+versatile
   pivot — pick the next phase/tier after 07's "make-it-yours + trust"). Candidates parked in
   the plan: Modal load-bearing program (eval-sweep/ADMET/durable-loop, GATE A), expensive
   top-K rescore-report (docking, Phase-2), or further trust/observability depth.
2. Synthesize `docs/08-<name>/milestone.md` + `handoff.md` only when that work starts — do not
   pre-create.

## What shipped this session (07-08 UI + full-workbench redesign)
Built via a `meta-plugin:agent-team` Builder↔Critic loop on **fable-5** (3 build rounds / 2
critic passes; orchestrator ran the Playwright `-shot` harness as the pixel oracle and
re-verified every gate). All under `apps/web` — no backend change (every API already existed).
- Objective builder · rich seed-import · quality/diversity/novelty display · manifest + CSV/SDF
  downloads · cockpit reconnect-with-backoff + cold-start · redesigned Overview/Runs/Compare/Shell.
- New `--primary-hover` token (darken-on-hover) for WCAG-AA compliance.
- See `log.md` (2026-07-06 entry) for the four Critic-caught fixes (false gen-0 baseline delta,
  silent reconnect data-loss, unwired server-rejected-SMILES, hover-contrast AA miss).

## Current state
- **Milestone 07 COMPLETE** (01 mode-split · 02 seed · 03 pluggable-oracle · 04 objective ·
  04b constraints · 05 quality+trust · 06 manifest · 07 export · 08 authoring-UI). Alembic head
  **`38f369ef45a6`**.
- Gates green at ship: web typecheck + ESLint · **80 vitest** · `build` ✓ · **24 shots** @1280px
  (light+dark, no h-scroll) · **axe 16/16** WCAG-AA. Backend gates unchanged from 07-08-wiring
  (mypy 66 · ruff · 396 backend · migration drift).
- The 07-08 UI work landed on branch `m07-08-workbench-ui` and was merged to `main` in the ship
  commit (UI + these doc flips together).

## Active concerns / carry-forward
- **Reconnect residual:** the cockpit re-fetches on reconnect, closing the gap to a sub-second
  fetch→subscribe window; a true zero-gap fix needs **server-side WS event replay** (backend).
  Consider it if milestone 08 touches reliability/observability.
- The screenshot harness (`e2e/*-shot.spec.ts` + `_fixtures.ts`) mocks the whole API — no
  Postgres/Modal needed; it's the frontend iteration oracle. Extend fixtures when adding surfaces.
- Honesty invariants intact on every surface (mode badge, exploratory="not benchmark-comparable",
  figure-canon never "21/23", in-silico framing). Keep them on any new surface.
