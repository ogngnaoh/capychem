# Handoff — Milestone 05 (Operator Workbench)

## Completed this session
- **CP0 approved** (milestone shape) and **CP1 approved** (slice 01 low-fi structure).
- **Slice 01 shipped:** low-fi wireframes of Overview + Workbench (running/completed) + hybrid launcher as throwaway `apps/web/app/proto/*` routes; §8 design questions resolved and **frozen in `01-decisions.md`**. Gate verified independently: 5/5 routes `scrollWidth=1280` (no h-scroll), typecheck clean (exit 0 after a round-2 fix of 4 `readonly`-array errors the Builder first mis-reported), honesty canon verbatim, boundary clean.
- Resolved operator decisions: NL resolver = LLM-backed/grounded/guardrailed (slice 03); cockpit baseline = Graph-GA reference line + live delta.

## Slice status across milestone
- 01 low-fi-wireframes → **shipped** (CP1 ✓)
- 02 hifi-surfaces-and-launcher → **in-progress** (Phase 2 starting)
- 03 productionize-and-wire → planned

## Current state
- Branch `main`. Slice 01 committed (docs + proto routes + `e2e/proto-shot.spec.ts`). Web dev server on :3000 serves `/proto/*`.
- Agent-team: Builder (`general-purpose`, reused for continuity) + a **fresh** Critic per round. Loop cap ~7.

## Next session start here
1. Drive **slice 02 (hi-fi)** via the Builder: evolve the `/proto/*` routes to hi-fi on-token (warm cream + coral restrained, Source Serif 4 @400 / Inter / Geist Mono; charts on `chart-1` + `muted-foreground` vars, no hardcoded hex); both hero surfaces + launcher + re-skin proto Runs/Compare; wire a dark-mode toggle; light **and** dark legible. Fresh Critic reviews vs spec §7 + binding constraints (now including full WCAG-AA + dark). Fix carried nits (AUC y-axis ticks, card rhythm).
2. Run to **⏸ Checkpoint 2 (visual)** for operator approval before productionizing (slice 03).

## Active concerns
- Slice 03 (large, may sub-split): intent-resolution backend (LLM, grounded, guardrailed, cost-tracked) + **RDKit server-SVG** for 2D structures (`structure_svg` field or `GET /molecule/svg`) + surface missing read-fields (valid-SMILES rate, GA baseline, cost) + productionize `/proto/*` into real routes on live REST/WS + full a11y/verify.
- Data gaps: no valid-SMILES rate / cost split / GA baseline in `RunSnapshot`; WS has no per-candidate streaming — cockpit stays generation-level; do not touch the loop.
- Honest-figure canon: **21 of 21 comparable, 2 of 23 excluded-for-cause** — never "21/23". Source: `docs/04-compare-and-polish/g1-full23-10k-seed42.json`.
- Builder is `general-purpose` (has Skill/Agent); boundary prose-enforced — Critic confirms only `proto/**` + the e2e spec touched.
