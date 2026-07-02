# Milestone 05 — Operator Workbench (UI/UX legibility redesign)

> SPEC Phase 4+ (post-G1 showcase). Backs the approved design spec
> `docs/superpowers/specs/2026-07-02-capychem-operator-workbench-design.md`.
> The engine is shipped (G1–G3 met); this milestone makes it **legible**, not more capable.
> Driven by a superpowers **agent-team** (Builder ↔ Critic) + the **frontend-design** skill,
> paused at four human checkpoints. Reuse-first: no new agents/commands/hooks.

## Goal

Restructure the web app into an operator **workbench** — a console-with-a-home where a non-chemist
grasps what CapyChem does within ~15s, the agent's reasoning and the beat-Graph-GA rigor are
unmissable (not buried), and runs are launched by **objective**, not GA knobs — all on the existing
tokens, honest about being an in-silico demonstrator.

## Scope

- **Persistent shell + IA:** `Overview · Workbench · Runs · Compare` (net-new; no shell exists today; `sidebar-*` tokens already defined but unused). Wire a dark-mode toggle (full `.dark` palette exists, no toggle).
- **Overview (home):** what-is-this hero; the loop visualized with **analyze** emphasized; honest **rigor strip** (the 21-of-21-comparable figure, in-silico framing); entry into the launcher; objective-catalog peek. Leaves a seam for future "your investigations."
- **Workbench cockpit (the star):** vitals row; AUC panel with **Graph-GA reference line + live beating-by/behind-by delta**; top molecules as **2D structure + SMILES + score**; **analyzer reasoning in prime real estate** (current hypothesis + timeline); running → completed states.
- **Hybrid intent launcher:** always-visible objective catalog (23 PMO tasks, plain-language groups) + NL box → **LLM-backed, catalog-grounded, guardrailed resolver** → **editable resolved plan** (objective/budget/strategy/plateau) → validation + refusal with a specific reason (FR-015) → projected oracle-call/cost envelope before launch.
- **Re-skin Runs + Compare** into the shell/tokens (keep Runs a dense scannable table; Compare overlays AUC coral=A / chart-2=B + side-by-side top-K + per-run stats). Replace hardcoded chart hex with `chart-1..5` tokens.
- **Backend (deliberately beyond "one thin step," per operator direction):** the grounded intent-resolution workflow (endpoint + guardrails + cost tracking); surface the cockpit's missing read-fields (valid-SMILES rate, per-task GA baseline reference value, cost) — no change to the optimization loop or oracles.
- **2D structure rendering:** approach chosen in the Phase-1 design loop (RDKit-JS vs server SVG vs placeholder motif).

## Non-goals (deferred, not precluded)

1. **Multi-run campaign / "investigations" grouping** — single-run MVP; leave the seam, don't build it.
2. **Conversational mid-run steering** — breaks benchmark purity + reopens the loop; if ever built, a clearly-labeled non-benchmark mode.
3. **New oracles / multi-objective / any optimization-loop or scoring change** — the engine is frozen; the only backend additions are the intent-resolution workflow + read-surfacing of already-computed data.
4. **New visual language or new tokens** — strictly the existing `globals.css` tokens; serif headings @400; coral restrained.
5. **Web deployment** — showcase = the repo + demo GIFs.
6. **Any real-world drug-discovery efficacy claim** — every number is an in-silico oracle/benchmark score (PRD N6).

## Slices (execution order)

1. **`01-low-fi-wireframes`** — interactive low-fi prototype pages of the two hero surfaces (Overview + Workbench cockpit) to settle structure cheaply, resolving the spec §8 design open questions. Builder ↔ Critic → **✓ CHECKPOINT 1** (structure). *shipped (CP1 approved 2026-07-02; §8 decisions frozen in `01-decisions.md`)*
2. **`02-hifi-surfaces-and-launcher`** — hi-fi on-token pass of both hero surfaces + the hybrid launcher UI + re-skin Runs/Compare to the shell (prototype-fidelity data; not yet wired live). Builder ↔ Critic → **⏸ CHECKPOINT 2** (visual). *in-progress*
3. **`03-productionize-and-wire`** — build the grounded intent-resolution backend + guardrails + cost; surface the cockpit's missing read-fields; productionize the surfaces into the real routes wired to the live REST/WS; full verify (typecheck, tests, 1280px screenshots of running/completed/empty, a11y light+dark). Builder ↔ Critic (may split Critic+Evaluator — high-stakes) → **⏸ CHECKPOINT 3** (ship gate). *planned*

*(Per project convention, milestone slices stay high-level; per-slice implementation detail lives in each slice's own session. Slice 03 is large and may sub-split when detailed.)*

## Integration notes

- **Current surface (ground truth, mapped 2026-07-02):** exactly 4 routes (`/` launch form, `/runs`, `/runs/[id]` = `LiveRun`, `/compare`); components `RunsBrowse`, `LiveRun`, `HypothesisSection`, `CompareView` + shadcn/base-ui primitives (`badge/button/card/input/label/table`); logic in `apps/web/lib/` (`api.ts`, `runEvents.ts`, `plateau.ts`, `utils.ts`); `*.test.tsx` beside each component.
- **Tokens/fonts:** OKLCH warm-cream + coral (`--primary` hue 46), Source Serif 4 @400 / Inter / Geist Mono, full light+dark palettes. **Chart strokes are hardcoded hex** (`#cc785c`, `#d97757`, `#6a9bcc`) — replace with `chart-1..5` in the re-skin.
- **Data-contract gaps to bridge in slice 03:** (a) `RunSnapshot` lacks valid-SMILES rate (lives in the `run.complete` summary / `summary_json`) and a cost split (scalar `cost_so_far_usd` only); (b) no GA baseline in the payload — the cockpit reference line reads each task's **committed final `graph_ga_auc`** from `docs/04-compare-and-polish/g1-full23-10k-seed42.json` as a static per-task lookup asset; (c) WS emits only `generation.complete`, `analyzer.hypothesis`, `run.complete`, `ping` — **no per-candidate streaming**; design the cockpit to generation-level granularity and avoid touching the loop.
- **Intent resolution (net-new):** endpoint that maps NL → one of the 23 tasks, **grounded** (can only return a real task or "no benchmark exists; closest is X"), RDKit-validates seed SMILES at the boundary, enforces positive/bounded budget, refuses with a named reason (FR-015), and is cost-tracked. LLM-backed with a deterministic guard/confirm layer; the editable mirror means a mis-map can never silently launch.
- **Honest-figure canon (never "21/23"):** *beats or matches vanilla Graph-GA on all 21 comparable PMO tasks by AUC of top-10 (single seed 42, 10,000-call budget); decisive (~0.1 AUC+) on 9; 2 of 23 excluded-for-cause (defective oracles, not losses); bar was ≥6/23.* Analyzer conditioning win = **+0.090 (seed 42) / +0.108 (seed 7) on jnk3** (single task; was negative before the redesign). Full-sweep spend $18.94. Source of truth: `g1-full23-10k-seed42.json`. Do not claim SOTA, multi-seed G1, universal analyzer value, or real-world efficacy.
- **Orchestration:** superpowers agent-team + frontend-design skill; orchestrator owns all milestone/handoff/slice/spec writes; teammates return structured results and never edit docs.

## Exit criteria (testable — spec §7)

1. From the Overview alone (no scrolling into a run) a non-chemist can state what CapyChem does and name the loop's 4 steps.
2. Launcher accepts **both** an NL intent and a catalog pick; both produce an editable resolved plan; invalid inputs (no objective / non-positive budget / invalid seed SMILES) are refused with a specific reason (FR-015). Catalog presents all 23 objectives grouped with plain-language descriptions.
3. Workbench, for a running **and** a completed run, shows: vitals; AUC with the Graph-GA reference line + delta; top molecules as 2D structure + SMILES + score; analyzer reasoning (current + timeline) in a prominent (not bottom) position.
4. Every score is labeled in-silico/oracle/benchmark; no efficacy claims anywhere.
5. All screens fit 1280px with **no horizontal scroll**; WCAG AA in light **and** dark; keyboard-navigable; status never by color alone; `prefers-reduced-motion` respected.
6. On-token: existing `globals.css` tokens only; serif headings @400; coral restrained to primary actions / live state / the "this run" series.
7. Four checkpoints passed (0 shape · 1 structure · 2 visual · 3 ship). When the milestone ships, milestone/handoff/slice status flips land in one commit on the main-flow branch.
