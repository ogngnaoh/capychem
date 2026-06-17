# Slice 03 — modal-llm-propose-endpoint

**Status:** in-progress · **Milestone:** 02 `end-to-end-loop` · **Deps:** none · **Consumed by:** slice 04

## Goal

Stand up the proposer-serving half: a Modal `propose()` function (DeepSeek-v4-pro via its
OpenAI-compatible API) + a modern async client adapter that returns proposed SMILES + per-call token
cost — mirroring the existing oracle pattern. Leads the milestone to front-load the Modal+LLM
integration risk.

## Plan

- **Design spec:** `docs/superpowers/specs/2026-06-17-modal-llm-propose-endpoint-design.md`
- **Implementation plan:** `docs/superpowers/plans/2026-06-17-modal-llm-propose-endpoint.md` (6 tasks, TDD)
- **Files:**
  - Create `packages/core/capychem/proposer.py` — env-selected backend adapter (`stub` default /
    `modal`), `ProposalResult`, `propose_batch_async`, token→USD cost, SMILES cleaning. Mirrors
    `oracle.py`.
  - Modify `apps/worker/app.py` — thin `propose()` Modal function + `llm_image` + `propose_smoke`,
    beside the untouched `score()`.
  - Create `packages/core/tests/test_proposer.py` — stub determinism, monkeypatched modal path, cost,
    extraction, selector.
- **Decisions:** wrap DeepSeek API in Modal (GPU self-host designed-for, not built); prove the real
  path once (stub for CI + a one-time manual real-API smoke). Cleaning happens modern-side (worker
  returns `{raw, tokens_in, tokens_out}`).
- **Testing:** CI runs the stub (no network); the real path is verified once manually via
  `modal run … ::propose_smoke` with a `deepseek-api-key` Modal secret.

## Tasks

- [ ] T1 — `proposer.py` foundations: `ProposalResult`, `ProposerError`, config, `_clean_smiles` (+test)
- [ ] T2 — stub backend + `propose_batch_async` dispatch (+ stub/unknown tests)
- [ ] T3 — modal backend: token→USD cost + malformed handling (+ modal tests)
- [ ] T4 — Modal `propose()` worker function + `llm_image` + `propose_smoke`
- [ ] T5 — full quality gate (pytest / mypy / ruff / format; whole-suite regression check)
- [ ] T6 — one-time manual real-API smoke (Modal secret + `modal run`) — retires the integration risk

## Notes

- **Secret hygiene:** the DeepSeek key lives only in the Modal secret store / env — **never committed**
  (critical constraint).
- **Real-API unknowns surfaced by the manual smoke:** whether DeepSeek honors `n` (multiple choices)
  and `seed` per request; adjust the worker payload if not.
- **Contract for slice 04:** `propose_batch_async` returns cleaned candidate strings, NOT validated
  molecules — slice 04's `validate` node does RDKit validation; invalid strings trigger the Graph-GA
  fallback. `temperature`/`seed` are first-class so slice 04 can pin them for G6.
- **Cost:** slice 03 only *returns* `cost_usd`; populating `RunCost.llm_cost_usd` + the gate rewire is
  slice 05.
