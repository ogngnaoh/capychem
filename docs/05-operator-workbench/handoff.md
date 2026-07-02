# Handoff — Milestone 05 (Operator Workbench) — COMPLETE

## Completed this session
- **Milestone 05 shipped** — all 3 slices, 4 checkpoints (CP0 shape, CP1 structure, CP2 visual, CP3 ship). Operator approved CP0–CP2; CP3 driven autonomously via the revision-loop goal.
- **Slice 01** (low-fi wireframes) — §8 decisions frozen in `01-decisions.md`. Commit `cce5a66`.
- **Slice 02** (hi-fi on-token + dark toggle) — commit `36bc5c7`.
- **Slice 03a** (backend: `GET /catalog`, grounded/guardrailed `POST /intent/resolve` [deterministic + LLM seam], RDKit `GET /molecule/svg`, nullable `RunSnapshot` fields valid_smiles_rate/graph_ga_baseline/llm+oracle cost) — commit `8a74e89`. mypy strict clean, pytest 77, Critic PASS.
- **Slice 03b** (productionized `/proto/*` → real routes `/`,`/launch`,`/runs`,`/runs/[id]`,`/compare` on live REST/WS; real 2D structures; shell + dark toggle; `/proto` removed; tests updated) + a revision round (23-PMO spacing, seed-SMILES honesty caption, 23-task e2e fixture). typecheck 0, lint 0, vitest 30, e2e 17. Two synchronous Critics: PASS, 0 blocking.

## Slice status
- 01 low-fi-wireframes → shipped (CP1)
- 02 hifi-surfaces-and-launcher → shipped (CP2)
- 03 productionize-and-wire → shipped (CP3)

## Current state
- Branch `main`. Real app on the new design: `/` Overview · `/launch` hybrid launcher · `/runs` list · `/runs/[id]` live cockpit · `/compare`. Backend endpoints live on :8000. Web dev on :3000.
- Agent-team learning: `agent-team-*` subagents (and general-purpose mailbox *continuations*) only emit idle pings — **run reviewers synchronously** (`run_in_background:false`) to get their report; verify Builder claims independently (a Builder mis-reported typecheck once and skipped 2 of 3 revision items on a mailbox continuation).

## Next session start here
Milestone complete; project scope ends at 05. If continuing: (1) launch a *real* new run end-to-end (needs Modal/LLM up — `modal serve apps/worker/app.py`) to exercise the live launch→cockpit flow beyond mocks; (2) optional follow-ups: wire seed-SMILES population through `createRun`+loop (a deliberate non-goal this milestone), an automated axe a11y pass, and the LLM intent-resolution path (env-gated seam already in place).

## Active concerns / honest caveats
- **New-run launch needs Modal/LLM** (absent in this env). All read/browse/cockpit/compare surfaces are wired live against the ~290 existing Postgres runs (Critic loaded run 335 live); `launch.spec.ts` exercises launch→`/runs/{id}` against mocks.
- Intent resolver is deterministic here (grounded + guardrailed); LLM seam is env-gated and untested live.
- Pre-existing hardcoded hex in `components/ui/button.tsx` (not this milestone).
- Honest-figure canon: **21 of 21 comparable, 2 of 23 excluded-for-cause** — never "21/23".
