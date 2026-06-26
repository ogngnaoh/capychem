# Handoff — 02-end-to-end-loop (slice 03 fully closed; next = slice 04)

## Completed this session

- **Closed slice 03's real-API smoke (T6).** With a funded DeepSeek key, ran the `direct` backend
  end-to-end: 2 distinct, RDKit-valid SMILES + real per-request token counts + cost.
- **Fixed two bugs the real call surfaced** (branch `slice03-direct-proposer-n1-fanout`, TDD):
  1. **DeepSeek caps `n=1` per request** (`400 Invalid n value`) — `_direct_propose` now fans out
     **n concurrent single-choice requests**, each with a per-index seed (`seed+i`, G6-friendly) and its
     own token usage. No `n` in the payload; `_one_proposal_row` is the per-request unit.
  2. **Error hardening** (the previously-deferred item) — `_deepseek_chat` maps HTTP / non-JSON errors to
     a clean `ProposerError` that surfaces the response body; new `_post_deepseek` is the network seam.
- **Model id confirmed:** `deepseek-v4-pro` **is** live (`GET /models` lists `deepseek-v4-pro` +
  `deepseek-v4-flash`) and is the code default — real runs need **no** `CAPYCHEM_LLM_MODEL` override.
  (`deepseek-chat` aliases to the *flash* model, so pin the explicit `deepseek-v4-pro` id.)
- Gate green: pytest **75 passed**, mypy clean (29 files), ruff clean.

## Slice status across milestone

- `01-launch-and-watch-jnk3` → planned
- `02-plateau-stop-and-signal` → planned
- `03-modal-llm-propose-endpoint` → **shipped + real-API confirmed — frozen**
- `04-llm-proposer-with-ga-fallback` → planned (next)
- `05-unique-call-budget-and-cost-ledger` → planned
- `06-beat-graph-ga-on-jnk3` → planned

Build order: `01 ∥ 02 ∥ 03 → 04 → 05 → 06`.

## Current state

- Fix on branch `slice03-direct-proposer-n1-fanout` (merge to `main` + push when ready).
- `direct` proposer is the real path (no Modal). Real runs need: `CAPYCHEM_PROPOSER_BACKEND=direct` +
  funded `DEEPSEEK_API_KEY` (in `.env.local`); model defaults to `deepseek-v4-pro` (no override).
  `.env.local`'s default backend stays `stub` (slice 04 dev needs no key).
- Carried infra (m01): Langfuse v2 :3001, Postgres :5432, `CAPYCHEM_ORACLE_BACKEND` unset (local harness).
  Eval authority: `packages/core/capychem/eval/`.

## Next session start here

**Start slice 04 `llm-proposer-with-ga-fallback`** — next critical-path slice (consumes the proposer
adapter). Begin brainstorm → spec → plan; develops against the `stub` backend (no key). Slices 01 & 02 are
dependency-free and can slot in anytime. Kickoff prompt saved in the vault
(`prompts/handoff/2026-06-18-capychem-milestone-02-slice-04-llm-proposer-handoff.md`).

## Active concerns

- **Slice 04 is the heaviest** (abstraction + dual-reachability + LLM wiring + GA fallback + pinned
  determinism + valid-SMILES gate + spans). Watch size; split if >2 pages (verifier endorsed whole for now).
- **Async/sync seam** (slice 04): async LLM client vs synchronous headless eval path — needs a sync bridge
  for G6.
- **`valid_smiles {proposed, valid, rate}`** is a frozen contract (slice 04 reads, never reshapes).
- **Beat risk:** without the analyzer (m03) this is MOLLEO-minus-analysis; the LLM may not beat Graph-GA on
  jnk3 — that IS the week-7 kill-switch (narrow scope, don't abandon).
- **Modal worker `propose()` has the identical `n=1` latent bug** — deliberately deferred (no Modal to
  test); flagged in an `apps/worker/app.py` comment. Mirror the proposer fan-out if Modal returns.
- **SPEC drift:** Alt D locked Modal-served inference; `direct` is a conscious no-Modal re-decision. Revisit
  the SPEC line if Modal stays unavailable.

## Slice log

- 2026-06-16 — Milestone 02 scoped (agent-team planning; 6 slices, clean verifier sign-off).
- 2026-06-17 — Slice 03 design spec + implementation plan + slice doc (pre-code).
- 2026-06-18 — Slice 03 shipped (code; real-API smoke pending). Subagent-driven TDD; pytest 71; merged+pushed.
- 2026-06-19 — Slice 03 follow-up: Modal-free `direct` DeepSeek backend; pytest 73; commit `90d2b9c`.
- 2026-06-26 — **Slice 03 fully closed:** real-API smoke confirmed on the default `deepseek-v4-pro`;
  `n=1` fan-out + error-hardening fix (branch `slice03-direct-proposer-n1-fanout`); pytest 75.
