# Slice 03 — modal-llm-propose-endpoint

**Status:** shipped 2026-06-18 (code + stub-verified; real-API smoke pending) · FROZEN · **Milestone:** 02 `end-to-end-loop` · **Deps:** none · **Consumed by:** slice 04

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

- [x] T1 — `proposer.py` foundations: `ProposalResult`, `ProposerError`, config, `_clean_smiles` (+test)
- [x] T2 — stub backend + `propose_batch_async` dispatch (+ stub/unknown tests)
- [x] T3 — modal backend: token→USD cost + malformed handling (+ modal tests)
- [x] T4 — Modal `propose()` worker function + `llm_image` + `propose_smoke`
- [x] T5 — full quality gate (pytest 71 passed / mypy clean / ruff clean / format applied to new files)
- [x] T6 — one-time manual real-API smoke — **DONE (2026-06-26)** via the `direct` backend on the default
  `deepseek-v4-pro`: returned 2 distinct, RDKit-valid SMILES with real per-request token counts + cost.
  Surfaced (and fixed) the `n=1` constraint — see the 2026-06-26 follow-up.

## Follow-up — Modal-free `direct` backend (2026-06-19)

Modal turned out to be unavailable to the operator. Added a third proposer backend `direct` that calls
DeepSeek's OpenAI-compatible API straight from the local process via `httpx.AsyncClient` (key from the
`DEEPSEEK_API_KEY` env var) — mirroring the oracle's Modal-free `local` path. `modal` and `direct` now
share a `_rows_to_results` helper (cleaning + token→USD cost). Commit `90d2b9c`; tests 8 passed (added
`test_direct_backend_maps_response_and_cost`, `test_direct_backend_missing_key_raises`). Modal stays as
an optional future scaling path behind the same contract. **To run the real proposer locally:**
`export DEEPSEEK_API_KEY=… ; CAPYCHEM_PROPOSER_BACKEND=direct` then call `propose_batch_async`. The
model id is env-configurable (`CAPYCHEM_LLM_MODEL`, default `deepseek-v4-pro`) — point it at a valid
DeepSeek model if that id 404s.

**Deferred (when slice 04/06 runs the real loop):** ~~harden `direct` so a malformed/error DeepSeek body
(missing `choices`, or an HTTP error) raises a clean `ProposerError` instead of a raw `KeyError`/httpx
error~~ — **RESOLVED 2026-06-26** (see below).

## Follow-up — `n=1` fan-out + error hardening (2026-06-26)

The real-API smoke (T6) surfaced two things the stub couldn't:

1. **DeepSeek caps `n=1` per request** (`400 Invalid n value`). The `direct` backend sent `n` in one
   request, which broke every batch >1. Fixed by fanning out **n concurrent single-choice requests**
   (`asyncio.gather`), each with a **per-index seed (`seed+i`)** for distinct-yet-deterministic samples
   (G6-friendly), each carrying its own per-request token usage. `_direct_propose` now has no `n` in the
   payload; `_one_proposal_row` is the per-request unit.
2. **Error hardening (the deferred item).** `_deepseek_chat` now maps HTTP errors and non-JSON bodies to
   a clean `ProposerError` that surfaces the response text (so a 400 is legible, not a raw httpx
   traceback). New `_post_deepseek` is the network seam tests patch. `_one_proposal_row` also raises
   `ProposerError` on a missing `choices`/`content` body.

Also confirmed via `GET /models`: **both `deepseek-v4-pro` and `deepseek-v4-flash` are live**, and the
smoke ran on the default `deepseek-v4-pro` (`_DEFAULT_MODEL`) — no `CAPYCHEM_LLM_MODEL` override needed.
Caveat: `deepseek-chat` aliases to the *flash* model, so pin the explicit `deepseek-v4-pro` id rather than
the `-chat` alias. Tests: 75 passed (replaced the old single-request direct test; added fan-out + 2
error-path tests). mypy/ruff clean. **The Modal worker `propose()` has the identical `n=1` latent bug —
deliberately deferred** (no Modal access to test it); flagged in a code comment + the handoff.

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
