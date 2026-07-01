# Slice 05 — readme-and-langfuse-walkthrough

> Milestone 04 Track A — the **last** slice of the project. Documentation only, **$0 spend**
> (uses existing traced runs + the running local surface; no new loop, no LLM/oracle calls).
> Ships the flagship recruiter-legible README + a Langfuse trace walkthrough of the closed loop
> (propose → score → analyze → redesign), legible **without chemistry knowledge**. Folds in the
> G1 verdict with its honest denominator. Every score is an in-silico oracle score (PRD N6).

## Goal

A first-time reader (target: a big-tech intern recruiter skimming the GitHub repo) understands what
CapyChem is, sees the G1 result stated honestly, and can follow one real closed-loop run's decisions
in a Langfuse trace — all without any chemistry background. (Milestone Exit criterion #6; G3.)

**Verifiable success criteria:**
1. Root `README.md` exists and renders on GitHub: hero screenshot, what-it-is (no chemistry), honest
   G1 results, mermaid closed-loop + architecture diagrams, quickstart, in-silico disclaimer (N6).
2. `docs/langfuse-walkthrough.md` walks ONE real run's trace (propose → score → analyze → redesign)
   with annotated Langfuse screenshots; a non-chemist can follow the agent's decisions.
3. G1 framing is EXACT and honest: "beat or matched vanilla Graph-GA on all **21 reproducible** PMO
   tasks (single seed, 10k-call budget), decisively (>0.1 AUC) on **9**." Bar ≥6 of 23; denominator 23;
   **2 excluded-for-cause** (sitagliptin_mpo out-of-[0,1] oracle; valsartan_smarts GA 0.757 vs
   published 0.000). Single-seed caveat + 4 thin margins (qed/deco_hop/zaleplon/drd2 <0.03) stated.
   **Never "22/22", never SOTA, never real-world efficacy.**
4. Screenshots show the Anthropic-themed surface (cream+coral, Source Serif 4 / Inter).
5. A frontend Builder↔Critic loop confirms the UI-as-shown converges to the Anthropic design system
   (PASS) before ship.
6. Gates green: pytest · mypy (`-p capychem -p capychem.api`) · ruff; web vitest/tsc/eslint.

## Plan

**Featured run for the walkthrough:** run **271** (`qed`, LLM proposer, closed-loop). Rising AUC
0.82→0.94 over 80 oracle calls, 10 top molecules, 7 chemistry-light analyzer hypotheses. Its Langfuse
trace carries the full span tree (`node:propose/validate/score/analyze/persist`, `llm:propose`,
`llm:analyze`, `node:fallback`, `node:stop_check`).

**Files to touch (all new; no source changes expected):**
- `README.md` (root) — landing page.
- `docs/langfuse-walkthrough.md` — annotated trace narration.
- `docs/assets/*.png` — committed screenshots (web + Langfuse).
- This slice doc (planning record).

**Method (recommended, operator-approved):**
1. Bring up the surface locally ($0): FastAPI `:8000` (→ `capychem-postgres`), Next.js `:3000`;
   Langfuse already up on `:3001`.
2. Capture real screenshots via Chrome: run-detail hero (AUC + molecules), compare view, browse list,
   live-run; Langfuse full trace tree + `propose`/`score`/`analyze`/`fallback` spans.
3. Write README + walkthrough; embed the honest G1 table from `g1-full23-10k-seed42.json`.
4. **Frontend Builder↔Critic loop** — a frontend-design Critic reviews UI convergence to the Anthropic
   style; Builder applies any polish; iterate until PASS.
5. Gates green, then ship ritual.

## Tasks

- [x] Write this slice doc (goal plan).
- [x] Bring up FastAPI + Next.js locally; confirm run 271 renders on run-detail.
- [x] Compare pair confirmed: LLM run **271** vs Graph-GA run **3** (both qed) — an honest LLM-vs-GA demo.
- [x] Capture web screenshots (run-detail full/chart/analyzer/molecules/header, browse, compare, launch)
      → `docs/assets/`. Captured via headless Playwright at exact 1280px / 2× (the ultrawide window
      wouldn't resize; `save_to_disk` from the MCP browser wasn't reachable on disk — Playwright gave
      pixel control + correct output paths).
- [x] **Trace-link (FR-014) added to scope** (operator-approved during execution — closes an unmet FR and
      makes the app→observability path clickable). TDD: `config.trace_url()` + `GET /trace/{run_id}` route
      + `trace_url` on the snapshot + persist trace_id into `summary_json` (no schema change) + "View trace"
      link on run-detail. 8 backend + 2 web tests. Documented `LANGFUSE_PROJECT_ID` in `.env.example`.
      Backfilled run 271's real trace id for the demo.
- [x] Write `README.md` — all sections; honest G1 table; mermaid diagrams; quickstart; N6 disclaimer.
- [x] Write `docs/langfuse-walkthrough.md` — real trace 271 narrated span-by-span (tree, gen-1 timings incl.
      the 395 ms fallback firing, hypothesis evolution, 0.822→0.943 AUC lift).
- [x] Inner loop: self-reviewed screenshots vs the frontend-design rubric (framing/zoom tuned for crisp,
      on-brand crops).
- [x] Frontend Critic → **PASS** on Anthropic-style convergence (tokens verified wired; 3 minor+defensible
      nits, no blockers — accepted as-is, no churn to the twice-reviewed re-skin).
- [x] Gates: **pytest 250 · mypy 37 · ruff clean; web vitest 28 · tsc · eslint** — all green.
- [x] Captured the Langfuse trace-tree screenshot (`docs/assets/langfuse-trace-tree.png`) — operator toggled
      run 271's trace Public; headless capture reframed on generation:1 so the `node:analyze → llm:analyze`
      spans (the differentiator) are visible. Operator flips it back to Private after.
- [x] Ship ritual: froze this doc; marked milestone 04 **shipped** in `docs/milestones.md` (project scope ends
      — no next milestone); overwrote handoff; dated log line. **Merge to main + push are the operator's call.**

## Notes

- **$0 spend, no source changes intended.** Any UI polish surfaced by the critic loop is the only
  code that may change; keep it surgical (this is "compare-and-polish", not new capability).
- **Honesty is the thesis** (PROJECT.md). The G1 headline crushes the ≥6 bar without overclaiming.
  Two exclusions stated plainly as pinned-legacy oracle-semantic defects, excluded not fixed.
- **Backend posture** (memory: backend-headline decision): "designed for expensive oracles, shown on
  cheap ones" — surface the caching / unique-call budget / cost-ledger layer, don't oversell it.
- **Analyzer is the differentiator** — MOLLEO has no analyze step; the walkthrough must make the
  analyze→redesign conditioning visible and legible.
- Langfuse UI login: use the browser's existing Chrome session; if not authenticated, ask operator.
- Push is the operator's call; `main` is ahead of `origin` (unpushed slices 01–04 + re-skin). Confirm.
</content>
</invoke>
