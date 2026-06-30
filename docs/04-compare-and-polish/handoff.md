# Handoff — 04-compare-and-polish

## Completed this session

- **Milestone 04 planned and synthesized** (kickoff from `personal-vault/prompts/kickoff/2026-06-30-…-milestone-04-…`).
  Ran STEP 0 context load + a code-surface verification probe; confirmed `docs/04-compare-and-polish/` was
  greenfield. Wrote `milestone.md` (Goal / Scope / 7 Non-goals / 5-slice index / Integration notes / 7 Exit
  criteria) + this handoff as single writer. High-level only; per-slice docs written when each slice starts.
- **Code surface verified (2026-06-30):** no `GET /runs` list endpoint, no `/compare`, no browse page, no
  compare view → FR-010 + FR-012 both in scope. `RunSnapshot` already carries every compare-payload field
  → no DB schema change expected.
- **Scope decision resolved with the operator:** the G1 ≥6/23 full-23 sweep (Track B) is **in** milestone 04.
  Operator **topped up the DeepSeek balance on 2026-06-30** to fund the full denominator (prior balance ≈ $2.91).

## Slice status across milestone

- 01 `runs-list-and-browse` → planned (start here)
- 02 `compare-runs` → planned
- 03 `web-polish` → planned
- 04 `g1-full-23-sweep` → planned (independent of Track A; before 05)
- 05 `readme-and-langfuse-walkthrough` → planned (last)

## Current state

- Branch `main @ 7950ba3` — clean, pushed, in sync with `origin` (milestone 03 complete).
- `docs/milestones.md` already marks `04-compare-and-polish ← active` (no change needed).
- DeepSeek balance topped up for the full-23 sweep. Cost anchor: ~$0.8-1.0 per normal task at budget=10000;
  full-23 ≈ $25-30 fresh, or ~$13-16 if the 7 clean week-8 results are reused (deterministic per G6).

## Next session start here

- **Begin slice 01 `runs-list-and-browse`** (FR-010, Story 3). Synthesize `docs/04-compare-and-polish/01-runs-list-and-browse.md`
  when that slice's work starts (do NOT pre-create). First action: `GET /runs` list endpoint in
  `apps/api/.../routes_runs.py` + list-item schema in `schemas.py` + a web browse page in `apps/web/app/`.
  Sortable/filterable by status · best_score · oracle_calls · started_at.

## Active concerns

- **Track B pre-sweep guards are mandatory, not optional.** A full-23 sweep WILL re-hit both: (1) median2
  Graph-GA `crossover.py:142` `IndexError` (guard empty `RunReactants`); (2) sitagliptin_mpo oracle NaN
  (add `math.isnan` measurement guard) — the NaN guard is also a cost fix (unguarded it drove 229 gens).
  Land both before the sweep, or it degrades exactly as the week-8 run did.
- **Honesty bar (real audience = recruiter):** the README must state how many of 23 were evaluated; no
  real-world efficacy claim (PRD N6); compare adds no scoring.
- **Carried minors from m03** (opportunistic only): 5 cosmetic/coverage follow-ups; the pre-existing
  `LiveRun` GET→WS subscribe gap (self-heals).
- **AUC resampling** to a common oracle-call x-axis (SPEC §6.4d) is a real slice-02 design concern — name
  and test it, don't bolt it on.

## Slice log

- 2026-06-30 — Milestone 04 kicked off and planned; breakdown approved; DeepSeek topped up for the G1 full-23 sweep.
