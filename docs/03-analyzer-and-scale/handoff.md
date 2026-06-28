# Handoff — 03-analyzer-and-scale (MILESTONE KICKOFF — no code yet)

## Completed this session

- **Milestone 03 set up.** Synthesized `docs/03-analyzer-and-scale/milestone.md` (goal / scope / 6
  non-goals / 5 slices / integration notes / 10 exit criteria) + this handoff. `docs/milestones.md`
  already marks 03 `← active`. No code touched.
- **Grounded the plan in the code.** Mapped the analyzer's slot-in points: `analyze` node after
  `persist` in `loop/graph.py`; `AnalyzerHypothesis` reserved in `db/models.py`; `build_prompt` in
  `loop/strategy.py` (no hypothesis arg yet); head-to-head template in `eval/beat.py`; task allow-list
  {qed,jnk3} in `CreateRunRequest`; harness oracle already task-agnostic (`Oracle(name=task)`); the
  cost gate (`cost.cost_cap_usd()`) already fires in `apps/api/.../runner.py`.

## Slice status across milestone

- 01 `analyzer-agent` → planned (next)
- 02 `analyzer-value-verdict` → planned (deps 01)
- 03 `analyzer-live-surface` → planned (deps 01)
- 04 `twenty-three-task-surface` → planned (deps none)
- 05 `week-8-sweep-and-gate` → planned (deps 01, 04)

## Current state

- `main` @ `5db934e`, in sync with `origin/main` (remote is the source of truth). No feature branch yet.
- DeepSeek balance ≈ $2.37 (`.env.local` = `direct` / `deepseek-v4-pro`, key valid). Analyzer work will
  spend on this key — budget tiny, prefer the `stub` backend for dev/tests, real API only for verdicts.

## Next session start here

1. **Start slice 01 `analyzer-agent`** — the differentiator. Begin with `superpowers:brainstorming`
   (design the analyzer: hypothesis schema, top-k/bottom-k summary shape, **reasoning on/off**, prompt
   conditioning, malformed-output fallback), then `superpowers:writing-plans`, then write the slice doc
   `docs/03-analyzer-and-scale/01-analyzer-agent.md`. Build it into BOTH the product loop and the
   headless eval path (G6 parity) so slice 02's with/without verdict is apples-to-apples.

## Active concerns

- **DeepSeek v4 reasoning decision** ([[project_deepseek_v4_reasoning_default]]): the analyzer uses the
  SAME model as the proposer but may WANT reasoning ON and needs a larger output-token budget — decide
  consciously, do NOT copy the proposer's `thinking:disabled` / 128-cap payload.
- **First additive migration:** adding `AnalyzerHypothesis` is the first schema change since
  `create_all` bootstrap — decide create_all vs Alembic in slice 01 (models.py docstring flags it).
- **Both-paths parity (G6):** the headless `run_reproduction` has no analyze step — needs a sync
  analyzer bridge, or the with/without verdict won't be byte-identical.
- **Deferred from milestone 02:** manual live-UI plateau-callout check (small `plateau_window`, large
  budget); optional `plateauNotice` double-call hoist in `LiveRun.tsx` (Minor).

## Slice log

- 2026-06-28 — Milestone 03 kicked off; milestone.md + handoff synthesized. No slices shipped yet.
