# Handoff — Milestone 08 (backend systems depth + reframe) — SHIPPED

## Next session start here
Milestone 08 is **shipped and merged to `main`** (2026-07-07). No active milestone. If starting new work, pick the next milestone from `docs/milestones.md` and synthesize its folder per `~/.claude/CLAUDE.md`. The most likely next threads (all optional): the deferred cache-resume fix below, or the S8 docking stretch (needs re-scoping/approval).

## Current state
- Branch `m08-backend-systems-depth` merged into `main`. All 7 slices shipped (S1, S2, S2b, S3, S4, S5, S6, S7). Full suite **438 passed**; ruff/mypy clean (73 files).
- The engine is now durable + distributed-on-Postgres: `POST /runs` enqueues → SKIP-LOCKED lease/heartbeat/reclaim worker (inline for dev, standalone `apps/runner` for prod) with fencing → cross-process `LISTEN/NOTIFY` events → persistent exploratory oracle cache → backpressure + pagination + idempotency → Dockerized compose (`infra/Dockerfile`, `infra/compose.yml`) with `/readyz`. README leads with the backend; `docs/architecture.md` is the deep reference.
- Migrations head `9fa6b5f041b2`. Not pushed to any remote (local merge only) — push when ready.

## Active concerns / deferred follow-ups
- **Deferred (operator-approved):** exploratory cache-hit ↔ resume `calls_used` divergence — a resumed exploratory run that had cache hits over-counts budget vs the live run. Non-corrupting, exploratory-only, benchmark/G1 safe. Fix: distinguish cache-hit candidates on resume (e.g. don't write an OracleCall for a hit + derive `calls_used` from real calls in `reconstruct_state`). Documented in `docs/architecture.md` §7.5.
- **Known residual (documented):** lease-fencing zombie-revival race can yield a spurious retryable `errored` on the legit owner (never corruption). `docs/architecture.md` §7.4. Closing it needs core-loop write-fencing — deliberately not done.
- **S8 docking** remains an uncommitted stretch; do not build without re-approval.
