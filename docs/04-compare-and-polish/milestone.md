# Milestone 04 — compare-and-polish

> SPEC Phase 4 — the **final** milestone. Single source of truth for this milestone. Synthesized
> 2026-06-30 at kickoff (milestone 03 complete, `main @ 7950ba3`). Per-slice docs (`NN-<slice>.md`) are
> written when that slice's work starts; this file stays high-level.
>
> **Binding quality bar.** The real audience is a big-tech intern recruiter skimming the GitHub repo +
> writeup — chemistry is the *frame*, not the substance. Every slice biases toward **recruiter-legible
> without chemistry knowledge**. Every score is an in-silico oracle score (PRD N6); no real-world
> drug-discovery efficacy claim, ever.

## Goal

Close the operator surface — **browse all runs, compare two side by side** (Story 3/4, FR-010/012/013) —
polish it to render cleanly at 1280px, establish the **G1 benchmark count** (beat vanilla Graph-GA on
**≥6 of 23** PMO tasks by AUC-of-top-10 under the 10,000-call budget), and ship a **recruiter-legible
README + Langfuse trace walkthroughs** that explain the closed loop without chemistry knowledge.

## Scope

Two tracks with different cost profiles. The G1 sweep (Track B) is **in** this milestone — the operator
topped up the DeepSeek balance on 2026-06-30 specifically to fund the full-23 denominator.

**Track A — compare + polish + writeup (no/low spend; SPEC §9 Phase 4 core):**
- **Runs list + browse** (FR-010) — `GET /runs` list endpoint (sortable/filterable by status · best_score
  · oracle_calls · started_at) + a web browse page. This is the surface you pick two runs to compare
  *from*; it does not exist yet (only `GET /runs/{id}` does).
- **Compare-runs flow** (FR-012/013, Story 4) — `GET /compare?a=&b=` returning both runs' top-K, AUC time
  series **resampled to a common oracle-call x-axis** (SPEC §6.4d), hypothesis sequences, and per-run
  oracle-call + compute-cost stats; a web compare view overlaying the AUC curves + side-by-side top-K.
  Read-only aggregation of two existing `RunSnapshot`s — **no new loop, no scoring, no WS** (completed
  runs → REST only).
- **Web polish** (NFR demo responsiveness, G3) — clean render at 1280px, no horizontal scroll on
  run-detail + compare.
- **Recruiter-legible README + Langfuse trace walkthroughs** (G3) — the closed-loop story
  (propose → score → analyze → redesign), legible without chemistry; uses existing traced runs, no new
  spend. States the G1 denominator honestly.

**Track B — G1 ≥6/23 full-23 sweep (funded by the 2026-06-30 top-up):**
- **Two mandatory pre-sweep harness guards** (a full-23 sweep re-hits both): (1) median2 Graph-GA
  `crossover.py:142` `IndexError` — guard empty `RunReactants`; (2) sitagliptin_mpo oracle NaN slipping
  past the measurement read — add a `math.isnan` guard. The NaN guard is *also* a cost fix: sitagliptin's
  unguarded NaN drove 229 generations (~3-4× a normal task, ~42% of the week-8 sweep's spend); guarded, it
  drops to normal-task cost.
- **Full-23 sweep** via the canonical `eval` module (`capychem-eval --all`, with-analyzer-LLM vs vanilla
  Graph-GA, budget=10000, seed=42) → establish the authoritative **≥6/23** count. The week-8 sweep already
  has **7 trustworthy beats** among 9 evaluated tasks (G1's ≥6 threshold is effectively met); this slice
  completes the denominator. A null result (<6/23) is a documented outcome, not a failure to hide.

## Non-goals

1. **New agent/loop/optimization capability** — milestone 04 adds none. Compare introduces no scoring and
   no new LLM calls; it is read-only aggregation over existing runs.
2. **Multi-objective / Pareto optimization** — PMO single-objective only (stretch).
3. **Expensive oracles (ADMET-AI / Vina / DiffDock)** — stretch; backend architected, not exercised.
4. **Memory/RAG over past successful mutations** (the ExLLM angle) — stretch.
5. **Any real-world drug-discovery efficacy claim** (PRD N6) — every score is an in-silico oracle score.
6. **Auth / multi-tenant** — single-user demo posture (PRD/SPEC N8).
7. **DB schema change for compare** — `RunSnapshot` already carries every compare-payload field
   (top_k, auc_curve, hypotheses, cost_so_far_usd); `summary_json` holds top_k + auc_curve for completed
   runs. No migration expected.

## Slices

Build order: `01 → 02 → 03` (Track A surface, in sequence); `04` is independent of Track A (run any time
before 05); `05` is **last** — it documents the finished surface and folds in the G1 number. Each is an
independently shippable vertical slice; per-slice docs are written when that slice's work starts.

01. `runs-list-and-browse` — `GET /runs` list endpoint (sort/filter by status · best_score · oracle_calls
    · started_at) + web browse page listing all runs, linking to run-detail and (later) compare
    (FR-010, Story 3). — shipped — deps: none
02. `compare-runs` — `GET /compare?a=&b=` (both runs' top-K, AUC resampled to a common oracle-call x-axis,
    hypothesis sequences, per-run oracle-call + cost stats) + web compare view overlaying AUC + side-by-side
    top-K (FR-012/013, Story 4). — next — deps: 01
03. `web-polish` — clean 1280px render, no horizontal scroll on run-detail + compare; demo-responsiveness
    pass across the surface (NFR, G3). — planned — deps: 02
04. `g1-full-23-sweep` — two harness pre-sweep guards (median2 `IndexError`; sitagliptin NaN) + authoritative
    `capychem-eval --all` with-analyzer-LLM vs Graph-GA sweep (budget=10000, seed=42) establishing the G1
    ≥6/23 count; run+verdict slice (G1). — planned — deps: none (Track A independent); before 05
05. `readme-and-langfuse-walkthrough` — recruiter-legible README + Langfuse trace walkthroughs of the closed
    loop, legible without chemistry; folds in the G1 verdict and states its denominator honestly (G3). —
    planned — deps: 01, 02, 03, 04 (documents the finished surface) — **last**

## Integration notes

- **Compare is read-only aggregation.** The compare payload is built from two existing `RunSnapshot`s —
  every field is already present: `top_k[{smiles,score}]`, `auc_curve[{oracle_calls,top10_mean}]`,
  `hypotheses[...]`, `cost_so_far_usd`, `oracle_calls_used`. No new loop, no scoring, no LLM/oracle call,
  no WS. Compare runs only on completed runs → REST-only.
- **AUC resampling (SPEC §6.4d) is a slice-02 concern, not an afterthought.** Both runs' `auc_curve` must be
  resampled to a **common oracle-call x-axis** before overlay so the curves are comparable. Name and test
  this explicitly. Compute AUC only via the canonical `packages/core/capychem/eval` module — never ad-hoc.
- **REST surface** — `apps/api/capychem/api/routes_runs.py` today has `POST /runs`, `GET /runs/{id}`,
  `POST /runs/{id}/stop`, `/healthz` (+ WS in `ws_runs.py`). Slice 01 adds `GET /runs` (list); slice 02
  adds `GET /compare`. Schemas live in `apps/api/capychem/api/schemas.py` (where `RunSnapshot` is defined) —
  add a list-item schema (slice 01) and a compare-payload schema (slice 02).
- **Frontend** — `apps/web/app/` today has `page.tsx` (launch) + `runs/[id]/page.tsx` (LiveRun detail).
  Slice 01 adds a browse page; slice 02 adds a compare page; slice 03 polishes run-detail + compare for
  1280px. No WS on the compare/browse paths.
- **Track B harness guards** — `harness/capychem_harness/graph_ga/crossover.py` (median2 `IndexError`,
  guard empty `RunReactants`) and a `math.isnan` measurement guard on the read path
  (`packages/core/capychem/eval` — `sweep.py` / `verdict.py` / `cli.py`). **Never import the harness; the
  bridge is subprocess + JSON only.** Measure G1 strictly via the canonical eval module.
- **Cost stays first-class.** Track B spend flows through the eval runner; per-run compute-cost is already
  on `RunSnapshot.cost_so_far_usd` / `RunCost`, surfaced in run-detail and (slice 02) compare. The
  milestone-02 `cost.cost_cap_usd()` gate is unchanged.
- **Carried follow-ups from milestone 03** (fold in opportunistically where a slice touches them; don't
  force): 5 cosmetic/coverage minors (m03 handoff "Active concerns"); the pre-existing `LiveRun` GET→WS
  subscribe gap (self-heals, identical to existing `generation.complete` semantics).

## Exit criteria

1. `GET /runs` returns the run list, sortable/filterable by status · best_score · oracle_calls ·
   started_at (FR-010); the web browse page lists all runs and links to run-detail and compare.
2. `GET /compare?a=&b=` returns both runs' top-K, AUC resampled to a **common oracle-call x-axis**,
   hypothesis sequences, and per-run oracle-call + cost stats (FR-012); the web compare view overlays the
   AUC curves and shows side-by-side top-K (Story 4).
3. Per-run compute-cost is surfaced in both run-detail and compare (FR-013).
4. Run-detail + compare render cleanly at 1280px with no horizontal scroll (NFR demo responsiveness, G3).
5. The full-23 G1 sweep runs via the canonical eval module with both harness anomalies guarded (all 23
   produce trustworthy rows); the **≥6/23** count is established and the G1 verdict rendered (≥6 → goal met;
   <6 → documented honestly, not hidden).
6. A recruiter-legible README + at least one Langfuse trace walkthrough explains the closed loop
   (propose → score → analyze → redesign) without chemistry knowledge, and states the G1 denominator
   plainly (how many of 23 were evaluated).
7. Gates green: pytest, mypy strict (both `-p`), ruff; web vitest, tsc, eslint.
