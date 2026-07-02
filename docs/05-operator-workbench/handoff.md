# Handoff — Milestone 05 (Operator Workbench)

## Completed this session
- **CP0/CP1/CP2 all approved.** Slices 01 (low-fi) + 02 (hi-fi) shipped.
- **Slice 01:** low-fi wireframes; §8 decisions frozen in `01-decisions.md`.
- **Slice 02:** hi-fi on-token pass of Overview + Workbench (running/completed) + Launcher + Runs/Compare re-skin + dark-mode toggle. Verified independently: typecheck 0, lint 0, Playwright 13/13 (1280px no-scroll light+dark), no hardcoded hex, honesty canon intact.
- Operator set a standing goal: **drive the agent loop through revision rounds autonomously until the output is approved** (no per-checkpoint pause).

## Slice status across milestone
- 01 low-fi-wireframes → **shipped** (CP1 ✓)
- 02 hifi-surfaces-and-launcher → **shipped** (CP2 ✓)
- 03 productionize-and-wire → **in-progress** (Phase 3 starting; may sub-split 03a/03b/03c)

## Current state
- Branch `main`. Slices 01–02 committed. Web dev server on :3000 serves `/proto/*` (hi-fi, light+dark).
- Agent-team: Builder (`general-purpose`, reused) + Critic (`agent-team-reviewer`). NOTE: background reviewers only emit idle pings via mailbox — **run the Critic synchronously** (`run_in_background:false`) in slice 03 to get its report; gate evidence otherwise gathered by orchestrator directly.

## Next session start here
Drive **slice 03 (productionize + backend)**, decomposed:
1. **03a backend:** grounded LLM intent-resolution endpoint (+ guardrails + cost); **RDKit server-SVG** for 2D structures (`structure_svg` field or `GET /molecule/svg`); surface missing read-fields (valid-SMILES rate, per-task GA baseline, cost) on `RunSnapshot`/schemas + `api.ts`.
2. **03b frontend:** productionize `/proto/*` into the real `/`, `/runs`, `/runs/[id]`, `/compare` wired to live REST/WS + new endpoints/fields; port proto components; update existing web tests; remove `/proto` scaffold once verified.
3. **03c verify:** end-to-end against real data (~290 runs in Postgres), a11y light+dark, 1280px screenshots of running/completed/empty on real routes, typecheck api+web, tests green → ⏸ Checkpoint 3 (ship).

## Active concerns
- Infra needed for 03: FastAPI :8000 + Postgres + (for intent resolution) an LLM path (Modal/DeepSeek) — probe availability; if the LLM path is unavailable in this env, ship a deterministic-fuzzy fallback behind the same grounded/guardrailed interface so the resolver still works, and leave the LLM upgrade seam.
- Productionizing replaces the working `LiveRun`/`RunsBrowse`/`CompareView` + their `*.test.tsx` — update tests alongside.
- Data gaps to fill in 03a: valid-SMILES rate (in `summary_json`), cost split (`RunCost`), GA baseline (from `g1-full23-10k-seed42.json`) — none currently on `RunSnapshot`.
- Honest-figure canon: **21 of 21 comparable, 2 of 23 excluded-for-cause** — never "21/23".
