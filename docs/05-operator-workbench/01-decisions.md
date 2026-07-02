# Slice 05.01 — Resolved §8 design decisions (frozen, CP1-approved 2026-07-02)

The design spec §8 open questions, resolved by building throwaway `/proto/*` low-fi
wireframes and reviewing 1280px screenshots. **Binding input for slices 02 (hi-fi) and
03 (productionize).** Each: decision · rationale · trade-off.

## 1. Cockpit hero at 1280px — reasoning vs AUC-vs-baseline + the no-scroll grid
**Decision.** Analyzer **reasoning is the hero** (wide left, `1.5fr`); **AUC-vs-Graph-GA is
co-primary** (right, `1fr`), both *above* a full-width top-molecules grid. Stack:
header → live loop-step pip → 5-tile vitals row → `[reasoning | AUC]` band (`h-[430px]`) → molecules.
**Rationale.** The analyze step is the differentiator (MOLLEO has none); the agent visibly
*reasoning* is the whole narrative, so it gets prime real estate. The beat-Graph-GA rigor is
the *proof*, so it sits beside it — streaming, with a horizontal GA reference line + a live
"Beating/Behind baseline by ±X" delta badge (the locked product decision, not a GA curve).
**Trade-off.** Narrower AUC chart; the delta badge carries the headline number so a compact
chart still reads. Reasoning panel is height-capped with an internal scroll on the earlier-
hypotheses list so history never blows the vertical rhythm.

## 2. Overview loop visualization — static vs live
**Decision.** **Static diagram on Overview**; **live current-step pip on the cockpit** (same
`LoopDiagram` component, `activeStep` prop). `propose → score → analyze → redesign → stop`,
`analyze` emphasized (coral + "the differentiator").
**Rationale.** Overview is the pre-run "what is this" surface — comprehension in ~15s wants a
stable diagram. Motion belongs where there's live state; animating a loop with no run implies
activity that isn't happening (dishonest).
**Trade-off.** Overview doesn't demonstrate liveness — fine, that's the cockpit's job. One
component avoids split-brain.

## 3. Catalog layout for a non-chemist
**Decision.** Four plain-language groups (Drug-likeness · Target activity · Rediscovery &
similarity · Multi-property/MPO), each a section with a one-line hint + a dense 2-col card grid;
every card = task name (mono) + one-line "what it measures"; a single per-catalog note
("scores 0–1, higher is better · in-silico") states "what a good score means" once. Blurbs
always visible at low-fi.
**Rationale.** Grouping by *intent* (what you'd ask for), not oracle mechanics, lets a non-
chemist scan the space. Always-visible blurbs match the legibility goal.
**Trade-off.** 23 open blurbs = a tall page (fine for a "browse everything" surface; Overview
shows only a 4-group peek). Progressive disclosure is the escape hatch if density bites in 02.

## 4. Launcher NL-resolution UX
**Decision.** Three zones: NL intent box with a *Resolve* action + grounded confidence line;
always-visible catalog as the possibility-space backdrop (resolved objective `selected`);
sticky **editable resolved-plan mirror** (objective + blurb, budget, plateau, strategy, optional
seed SMILES) + projected envelope + coral **Start run**. Guardrails render as an inline gallery,
one row per FR-015 refusal naming *which input* + *why*. No-match (`?state=nomatch`) swaps the
mirror for a grounded refusal ("closest is X … confirm before launch", **Start disabled**).
**Rationale.** A persistent editable mirror makes NL a *convenience, not a commitment* — you
always see/correct the resolved plan before launch. Grounding every resolution to the 23 real
oracles (refusing otherwise) is the honesty guardrail: runs only start against a real PMO oracle.
**Trade-off.** Two input modalities compete; resolved by role-splitting (catalog = possibility
space, NL = shortcut, mirror = the single commit surface). Guardrails shown as a static gallery
for review; real validation wires in slice 03.

## 5. 2D structure rendering — the dependency-driving decision
**Decision.** Low-fi uses a clean **placeholder motif** (dashed tile + neutral ring glyph,
`aria-hidden`). For 02/03, **recommend server-rendered RDKit SVG**, not RDKit-JS.
- **Server SVG (recommended):** the Python stack already has RDKit and validates every SMILES
  with it; `rdMolDraw2D.MolDraw2DSVG` is cheap, deterministic, cacheable per canonical SMILES.
  Deliver as a `structure_svg` field on `TopMolecule` **or** a `GET /molecule/svg?smiles=` endpoint.
  Light client bundle; depiction honest (same toolkit that scores). → **new slice-03 backend touch.**
- **RDKit-JS (rejected for MVP):** ~7–8 MB WASM + init latency + a new npm dep (this slice forbids
  deps); only earns its weight for client-side interactivity the showcase doesn't need.
**Trade-off.** Server SVG = a request/endpoint per structure, no client re-render; RDKit-JS =
rich in-browser interactivity at heavy bundle cost. For a static 2D depiction beside SMILES +
score, server SVG wins on bundle size, honesty, and reuse.

## Cross-cutting (carried into 02/03)
- **Honesty (N6):** every score labeled in-silico/oracle/benchmark; rigor strip uses the figure
  canon verbatim (21 comparable, decisive on 9, 2 excluded-for-cause, bar ≥6/23). No "21/23", no efficacy.
- **A11y affordances present as placeholders:** status = badge-text + pip, not color alone; live
  pulse is `motion-safe:` only; nav uses `aria-current`; structure tile `aria-hidden`. **Full
  WCAG-AA + dark-mode audit is a 02/03 task** (dark palette exists in `globals.css`, no toggle yet).
- **Charts:** `chart-1` (this-run, coral) + `muted-foreground` (dashed GA baseline) via CSS vars;
  no new tokens, no hardcoded hex. Instantaneous panel labeled "top-10 mean" (the AUC-integral
  claim stays on the Overview rigor strip where it's precise).
