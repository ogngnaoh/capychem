# Handoff — Milestone 08 (backend systems depth + reframe)

## Next session start here
Run the dynamic Workflow that builds S1→S7 with adversarial per-slice gates. Start sequence + slice contracts: `docs/superpowers/plans/2026-07-07-capychem-milestone-08-backend-depth.md`. The Workflow returns for human review AFTER S2 and AFTER S6 (before S7); resume with `Workflow({scriptPath, resumeFromRunId})`.

## Current state
- Branch `m08-backend-systems-depth` (off `main`); planning docs (spec + plan) committed on it.
- Milestone docs synthesized; `docs/milestones.md` entry 08 flipped to `← active`.
- Baseline verified gate-green in this env: `ruff` ✓, `mypy -p capychem -p capychem.api` ✓ (66 files), Postgres reachable (`capychem-postgres` on :5432), harness venv present (`harness/.venv`, Python 3.10), `.env.local` has DEEPSEEK key + backends. All slices **planned**, none started.
- `apps/runner/` does NOT yet exist (S2 creates it). No Dockerfile. `GET /runs` unpaginated. No persistent cache. `apps/api/tests/conftest.py` absent (S1 creates it).

## Active concerns
- **S2 is the risk.** Existing tests drive runs in-process (see milestone.md Integration notes). Out-of-process execution must not weaken guarantees; the inline-vs-standalone-worker separation is an operator-review call at the S2 hard gate.
- **S4 must not contaminate G1.** Cache at the async/loop layer only; benchmark trajectory identical on/off; `g1-full23-10k-seed42.json` untouched.
- **`LISTEN/NOTIFY` payload ≤ ~8 KB** — large `top_k` events likely can't ride the NOTIFY payload; notify a pointer, read the event from DB (S3).
- Slow LLM-path tests hit real DeepSeek (cost + ~180 s). Iterate on the targeted subset; run the full gate before declaring green.
- Orchestrator owns milestone/handoff/log writes at gates — not Workflow agents. Independently re-verify every Builder claim.
