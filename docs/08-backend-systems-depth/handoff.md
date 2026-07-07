# Handoff — Milestone 08 (backend systems depth + reframe)

## Next session start here
Resume the dynamic Workflow for **S3 (LISTEN/NOTIFY) → S4 (cache) → S5 (backpressure+REST) → S6 (ops)**, which returns at the hard gate after S6 (before S7). Resume: `Workflow({scriptPath: "<session>/workflows/scripts/m08-backend-depth-wf_9c57625c-d94.js", resumeFromRunId: "wf_9c57625c-d94"})` (S1/S2 replay from cache; the gate set was edited to drop S2). Slice contracts + start sequence: `docs/superpowers/plans/2026-07-07-capychem-milestone-08-backend-depth.md`.

## Current state
- Branch `m08-backend-systems-depth` (off `main`). **S1, S2, S2b shipped + gate-reviewed + committed** (7cd100e, 66e5764, a3f253d). Baseline green: ruff ✓, mypy ✓ (69 files), full suite 402 passed; S2+S2b-critical set re-verified independently (14 passed).
- Durable queue is live: `POST /runs` enqueues (`status="queued"`); a worker (inline in the API for dev/test via `CAPYCHEM_INLINE_WORKER`, default on; standalone `apps/runner` for prod) claims via `SELECT … FOR UPDATE SKIP LOCKED`, drives with a lease/heartbeat, and on crash a second worker reclaims via `reconstruct_state`. Fencing hardened (S2b).
- Queue logic: `packages/core/capychem/db/queue.py`. Worker: `apps/runner/capychem_runner/`. Lease columns + `UNIQUE(run_id,index)` on `packages/core/capychem/db/models.py`; migrations `2a691a218cd5` (lease cols) + `c89f6ae510ec` (unique gen) — head applied.

## Active concerns
- **S4 must not contaminate G1.** Cache at the async/loop layer only (never `score_smiles`); benchmark trajectory identical on/off; `g1-full23-10k-seed42.json` untouched. Eval path (`eval/runner.py`) is already separate — keep it that way.
- **S3 `LISTEN/NOTIFY` payload ≤ ~8 KB** — notify a pointer (run_id + kind + gen index), read the full event from DB.
- **Fencing residual race (document in S7 architecture doc, honestly):** in a pathological zombie-revival race the reclaimed-from worker could win a single gen persist and make the *legit* owner hit the UNIQUE violation → spurious retryable `errored` (never corruption). Closing it fully needs invasive core-loop fencing — deliberately not done. Frame as a "known failure mode + why it's acceptable" talking point.
- Slow LLM-path tests hit real DeepSeek (~340 s full suite). Iterate on the targeted subset; run the full gate before declaring green.
- Orchestrator owns milestone/handoff/log writes at gates; independently re-verify every Builder claim.
