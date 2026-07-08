# Handoff — Milestone 08 (backend systems depth + reframe)

## Next session start here
Run the final slice **S7 (reframe & docs)**: resume `Workflow({scriptPath: "<session>/workflows/scripts/m08-backend-depth-wf_9c57625c-d94.js", resumeFromRunId: "wf_9c57625c-d94"})` (S1–S6 replay from cache; S7 runs live; it's the last slice so the Workflow returns done). Then operator reviews the README/architecture framing before merge to `main`.

## Current state
- Branch `m08-backend-systems-depth`. **S1, S2, S2b, S3, S4, S5, S6 all shipped + gate-reviewed + committed** (7cd100e, 66e5764, a3f253d, 9b73a1c, b1e83da, 6762185, 907189d). Full suite **438 passed**; ruff/mypy clean (73 files) — independently re-verified.
- The system is now genuinely distributed-on-Postgres: `POST /runs` enqueues → SKIP-LOCKED lease/heartbeat/reclaim worker (inline for dev, standalone `apps/runner` for prod) with fencing → cross-process `LISTEN/NOTIFY` live events → persistent exploratory oracle cache → backpressure + pagination + idempotency → Dockerized compose with `/readyz`.
- Migrations head `9fa6b5f041b2` (lease cols → unique gen → oracle cache → idempotency key), applied.

## Active concerns
- **S7 must (a) lead with the backend + ELI5 the domain, (b) write `docs/architecture.md` (lifecycle, queue/lease/fencing protocol, cache design, cost gate, hard-problems), (c) preserve FIGURE CANON verbatim + N6, (d) NOT claim docking exists.** The S7 contract in the Workflow script was extended to require documenting two known limitations honestly: the lease-fencing residual race AND the exploratory-cache↔resume budget divergence (operator-approved deferral).
- **Deferred follow-up (post-milestone):** fix the exploratory cache-hit ↔ resume `calls_used` divergence (distinguish cache-hit candidates on resume). Non-corrupting, exploratory-only, benchmark/G1 safe.
- On S7 done: gate-green, merge to `main`, mark milestone shipped in `milestones.md`, write the next handoff.
