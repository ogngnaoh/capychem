# Log — Milestone 08 (backend systems depth + reframe)

Dated decisions/findings; rationale a diff can't show. Append-only.

## 2026-07-07 — S1+S2 shipped; S2 hard gate reviewed

- S1 (credibility) + S2 (durable queue + out-of-process worker) built by the dynamic Workflow (`wf_9c57625c-d94`); both passed independent Evaluators first try (0 repairs). Orchestrator independently re-verified S2: ruff/mypy clean, 12 S2-critical tests pass, the 4 heavily-changed route tests were faithfully *adapted* (assert the persisted row) not weakened.
- **Reconciliation decision (S2 tension): inline-worker accepted.** `POST /runs` enqueues only; a worker drives out of band. Dev/test run an inline worker task in the API (`CAPYCHEM_INLINE_WORKER`, default on); prod compose sets it 0 and runs the standalone `apps/runner`. Both use the identical `claim_next_run`/lease/drive path, so "the request handler doesn't drive loops" holds. Operator confirmed accept over strict separation.
- **Finding at the gate → S2b fencing (operator-approved, "harden now properly").** S2's `renew_lease` was owner-scoped but the renew loop never checked the result; a *revived zombie* (worker stalled past its 60 s lease TTL, reclaimed, then revived) could double-write / clobber the new owner's terminal row. True process *death* was already clean. Shipped S2b: `UNIQUE(run_id, index)` structural backstop + `finalize_run`/`release_run` owner-fenced + `renew_lease` returns rowcount>0 → stop-on-lost-lease. Re-verified independently (14 S2+S2b tests pass; migration `c89f6ae510ec` head; ruff/mypy clean).
- **Residual race (accepted, documented):** in the pathological revival race the reclaimed-from worker can win a single gen persist and make the legit owner hit the UNIQUE violation → spurious retryable `errored` (never corruption). Fully closing it needs invasive core-loop write-fencing (Option D) with real regression risk — deliberately not done. To be written up honestly in S7's `docs/architecture.md` as a known failure mode + rationale.
- Workflow gate set edited to drop `S2` (reviewed) so the resume proceeds to S3; hard gate after S6 (before S7) stands.
