# Slice 05.01 — Low-fi wireframes of the two hero surfaces

**Status:** shipped (CP1 approved 2026-07-02) · **Phase:** 1 (of the milestone's 3) · **Gate:** ✓ CHECKPOINT 1 (structure)

> Frozen. Resolved §8 design decisions → `01-decisions.md`. Prototype routes live under `apps/web/app/proto/*` (disposable; evolved in slice 02, productionized/removed in slice 03).

## Goal

Produce interactive **low-fi** prototype pages of the two hero surfaces — **Overview (home)** and the
**Workbench cockpit** — to settle *structure and information hierarchy* cheaply, and to resolve the
spec §8 design open questions, **before** any hi-fi/token work. Deliberately unstyled/grayscale so the
review is about layout and legibility, not color.

## Plan

- **Approach:** throwaway Next prototype routes under an isolated path (e.g. `apps/web/app/proto/overview` and `apps/web/app/proto/workbench`), clearly marked disposable, using **static mock data** shaped like the real `RunSnapshot` / catalog (no live API, no WS). These are removed or evolved into the real routes in slice 03 — never shipped as-is.
- **Data realism:** mirror the real payload shape from `apps/web/lib/api.ts` types and a representative run (e.g. `/runs/281` — LLM run with real analyzer hypotheses) so the layout is stress-tested against real content lengths (long SMILES, multi-line hypotheses, 10 top-K rows).
- **Fidelity:** structure only — boxes, labels, grayscale, placeholder molecule tiles. No final copy, no coral, no charts-polish. One chart can be a rough line to prove the AUC+baseline arrangement.
- **Loop:** Builder runs the frontend-design inner loop (rubric + run the page + **1280px screenshot**) each round, then hands to the Critic (fresh context) to score against the relevant spec §7 criteria + the binding constraints (1280px no-scroll, legibility, honesty labels present as placeholders, accessibility affordances). Cap ~7 rounds.

## Tasks

- [ ] Stand up the disposable prototype route scaffold + a mock-data module shaped like `RunSnapshot` + a 23-task catalog stub (grouped: drug-likeness · target activity · rediscovery/similarity · multi-property).
- [ ] **Overview** wireframe: hero one-liner + honest framing; the 4-step loop visual with **analyze** emphasized; rigor strip placeholder (21-of-21-comparable figure); "start a run" entry; catalog peek. Decide: static loop diagram vs a live "current step" indicator.
- [ ] **Workbench cockpit** wireframe at 1280px with **no scroll**: header (run·objective·status·strategy·Stop·trace); vitals row; AUC panel with the **GA reference line + delta**; top-molecules block (2D-structure tile placeholder + SMILES + score); **analyzer reasoning prominent (not bottom)**. Decide the grid: is **reasoning** or **AUC-vs-baseline** the hero, and the exact no-scroll arrangement.
- [ ] Wireframe the **launcher** flow enough to settle its UX: catalog layout for a non-chemist; NL box → editable resolved-plan mirror → guardrail/refusal messaging (FR-015).
- [ ] Resolve the spec §8 open questions and record the decision + trade-off for each (esp. **2D structure rendering approach** — pick one).
- [ ] Capture 1280px light-mode screenshots of both surfaces (and note where dark will need checking later).
- [ ] Critic pass green (structure legible, no-scroll verified by screenshot, honesty placeholders present) → assemble the CHECKPOINT-1 packet for operator approval.

## Notes / open questions to resolve here (spec §8)

- **Cockpit hero at 1280px:** reasoning vs AUC-vs-baseline as the dominant panel; exact no-scroll grid.
- **Overview loop viz:** static diagram vs live "current step" indicator during a run.
- **Catalog layout** that reads for a non-chemist (grouping, cards, disclosure).
- **Launcher NL-resolution UX:** how the editable mirror + guardrail messages render; how a low-confidence / no-match resolution is shown before the (real) backend exists (mock it).
- **2D structure rendering** approach (RDKit-JS in-browser vs server-rendered SVG vs clean placeholder motif) — pick one, note the trade-off; this drives a dependency decision for slice 02/03.
- Servers for screenshots: `uv run uvicorn capychem.api.main:app --port 8000` + `pnpm --filter web dev` (only needed to render the prototype route; mock data means the API can be down).
