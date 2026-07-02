# Design Spec — CapyChem Operator Workbench (UI/UX legibility redesign)

**Status:** Approved (brainstorm complete, 2026-07-02)
**Related:** ./../../../PRD.md · ./../../../SPEC.md · Stories US-1..US-4
**Supersedes framing of:** the current `apps/web` surface (bare launch form → run table → detail)
**Backs:** the "UI/UX showcase" milestone (project engine already shipped; G1–G3 met)

## 1. Problem

The engine is strong but **invisible**. The app lands on a bare "Launch an optimization" form — no statement of what CapyChem is, a wall of GA/LLM jargon (Offspring/gen, Mutation rate, Plateau window), and the differentiator (the analyze step) buried at the bottom of a run-detail page. A first-time viewer cannot tell what the tool does, why sample-efficiency matters, or that an agent is *reasoning* each generation. This is a **legibility** problem, not a capability gap.

## 2. Audience & framing

- **Real audience:** recruiters / hiring managers skimming the repo — the interface must be **legible without chemistry knowledge**.
- **Framing audience:** a drug-discovery scientist doing hit-to-lead / lead-optimization.
- **Three lenses, one spine.** The interface is built as **(#3) an operator console you *drive*** and surfaces the other two *inside* it: the agent's live reasoning **(#2)** and the beat-Graph-GA rigor **(#1)** are shown as the evidence you read while driving — not as separate tabs.
- **Honesty is a design asset (N6).** Every number is an **in-silico oracle / benchmark score**. Labels ("oracle score", "benchmark", "in-silico") are first-class and stated confidently — precision reads as rigor to a knowledgeable viewer.

## 3. Goals / non-goals (of this design)

**Goals**
- A newcomer understands *what CapyChem is* and *the loop* within ~15s of landing.
- The agent's reasoning and the benchmark rigor are unmissable, not buried.
- Launching a run is expressed in **objectives**, not GA knobs, with clear guidelines + guardrails.
- The app feels like a tool a scientist could *use*, while staying honest about being an in-silico demonstrator.

**Non-goals (deferred, not precluded)**
- Multi-run **campaign** / "investigations" grouping — MVP is single-run (design leaves the seam).
- **Conversational mid-run steering** — breaks benchmark purity + reopens backend; if ever built, a clearly-labeled non-benchmark "exploration mode".
- New oracles / multi-objective / any loop or backend change beyond one thin intent-resolution step.
- Web deployment — showcase = the repo + demo GIFs.

## 4. Locked decisions (the spine)

1. **Framing:** operator console you drive (#3); rigor (#1) + reasoning (#2) surfaced within it.
2. **IA:** **console with a home** — a persistent shell: **Overview · Workbench · Runs · Compare**.
3. **Front door:** **hybrid intent launcher** — NL box + always-visible objective catalog → editable resolved plan → validation/grounded-honesty guardrails.
4. **Scope:** single autonomous run (MVP); human-in-the-loop is the outer *campaign* loop, deferred but not designed out.
5. **Nature:** legibility/showcase milestone over the shipped engine; **no backend reopening** beyond a thin NL→objective resolution step.
6. **Design system:** the existing Anthropic-leaning tokens in `apps/web/app/globals.css` (warm cream + coral, Source Serif 4 @400 / Inter / Geist Mono, light+dark). No new visual language.

## 5. Surfaces

### 5.1 Overview (Home) — the "what is this" surface
- **Hero one-liner + honest framing:** an autonomous agent that designs, scores, and **reasons about** molecules to hit an objective in as few oracle calls as possible — benchmarked against Graph-GA on PMO (in-silico).
- **The loop, visualized:** propose → score → **analyze** → redesign → stop, with *analyze* emphasized (the differentiator).
- **Start a run** → into the hybrid launcher.
- **Objective catalog** (or a peek) — grounds "what can I ask for."
- **Rigor strip:** the honest beat-Graph-GA result (pull the exact figure from the eval reports — the comparable-set number, in-silico framing; do **not** invent "21/23") + recent runs. Leaves a home for "your investigations" later.

### 5.2 Workbench — the cockpit (the star), one run, live → completed
- **Header:** run · objective · status · strategy · **[Stop]** · trace link (`GET /trace/{run_id}`).
- **Vitals row:** generation · oracle calls / budget (progress) · best score · cost · valid-SMILES rate.
- **AUC panel** with the **Graph-GA baseline overlaid** — "are we beating the baseline?" (#1) lives *in* the cockpit, streaming.
- **Top molecules:** live 2D structures + SMILES (mono) + score; improved rows highlighted.
- **Analyzer reasoning — prime real estate** (#2): current hypothesis up front (focus/avoid), timeline of prior ones. Not the bottom of the page.
- **Two states:** running (live counters, respectful motion) → completed (settles into results + a placeholder seam for "spawn a follow-up").

### 5.3 Runs (browse) & 5.4 Compare
Largely exist (`/runs`, `/compare`). Re-skin to the shell + tokens; Runs stays a dense scannable table with status filter + two-row Compare selector; Compare overlays AUC (coral = A, chart-2 = B) + side-by-side top-K + per-run stats.

### 5.5 Hybrid launcher — input model
Four layers: **(1) possibility space** = objective catalog of the 23 PMO tasks, grouped in plain language (drug-likeness · target activity · rediscovery/similarity · multi-property), each with "what it measures / what a good score means"; **(2) intent** = NL, resolved against the catalog; **(3) mirror** = resolved run shown as editable options (objective, budget, strategy, plateau); **(4) guardrails** — objective must resolve to a real oracle (else "no benchmark exists; closest is X"); seed SMILES RDKit-validated at the boundary; budget positive/bounded; no objective → refuse; every refusal names *which* input and *why* (FR-015). Projected oracle-call/cost envelope shown before launch.

## 6. Cross-cutting
- **Accessibility:** WCAG AA contrast (light + dark); keyboard-navigable; status never by color alone; `prefers-reduced-motion` honored for live streaming/pulses.
- **In-silico honesty:** oracle/benchmark labels first-class; no real-world efficacy language anywhere (N6).
- **Design system:** on-token (`globals.css`); serif headings weight 400; coral restrained to primary actions / live state / the "this run" series; charts on `chart-1..5`.

## 7. Acceptance criteria (testable)
1. From the Overview alone (no scrolling into a run) a non-chemist can state what CapyChem does and name the loop's 4 steps.
2. Launcher accepts **both** an NL intent and a catalog pick; both produce an editable resolved plan; invalid inputs (no objective / non-positive budget / invalid seed SMILES) are refused with a specific reason (FR-015).
3. The catalog presents all 23 objectives grouped with plain-language descriptions.
4. Workbench, for a running **and** a completed run, shows: vitals, AUC with Graph-GA baseline overlay, top molecules as 2D structure + SMILES + score, and analyzer reasoning (current + timeline) in a prominent (not bottom) position.
5. Every score is labeled in-silico/oracle/benchmark; no efficacy claims present.
6. All screens fit 1280px with **no horizontal scroll**; WCAG AA in light+dark; keyboard-navigable; status not color-only; reduced-motion respected.
7. On-token: uses existing `globals.css` tokens; serif headings @400; coral restrained.

## 8. Open questions — the agent-team loop resolves these
- Cockpit grid at 1280px: is **reasoning** or **AUC-vs-baseline** the hero panel, and the exact arrangement with no scroll.
- Overview loop visualization: static diagram vs a live "current step" indicator during a run.
- Catalog layout that reads for a non-chemist (grouping, cards, disclosure).
- Launcher NL-resolution UX: how the editable mirror + guardrail messages render.
- **2D structure rendering** approach: RDKit-JS in the browser vs server-rendered SVG vs a clean placeholder motif (pick one; note the trade-off).

## 9. Repo touchpoints
- Web: `apps/web/app/` (routes `/`, `/runs`, `/runs/[id]`, `/compare`), `apps/web/components/`, `apps/web/lib/api.ts`, `apps/web/app/globals.css` (tokens), `apps/web/app/layout.tsx` (fonts).
- API (read-only for this milestone unless intent-resolution needs an endpoint): `apps/api/capychem/api/routes_runs.py`, `ws_runs.py`, `schemas.py`, `compare.py`, `config.py` (`trace_url`).
- Running locally: web :3000, api :8000 (Postgres has ~290 runs of real data to design against).
