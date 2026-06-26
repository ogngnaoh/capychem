# Slice 04 — llm-proposer-with-ga-fallback

**Status:** in-progress · **Milestone:** 02 `end-to-end-loop` (SPEC Phase 2) · **Deps:** 03 · **Consumed by:** 05, 06

**Design spec:** `docs/superpowers/specs/2026-06-26-llm-proposer-with-ga-fallback-design.md`
**Implementation plan:** `docs/superpowers/plans/2026-06-26-llm-proposer-with-ga-fallback.md`

## Goal

Wire an LLM proposer into the loop behind a `mutation_strategy`-selected abstraction, with a
deterministic Graph-GA fallback so generation throughput never drops on invalid LLM output (FR-005),
reachable from both the product loop and the headless eval runner (G6). Stub-only this slice.

## Plan

- **New `loop/strategy.py`** — shared, G6-sensitive pieces (`build_prompt`, `propose_llm_async`,
  `propose_llm_sync`, `ga_fill`, `fallback_fill`, `LLM_TEMPERATURE=0.7`) imported by both paths.
- **One new node** — `propose → validate → fallback → score → persist → stop_check`. The `validate`
  node stays the sole owner of the frozen `valid_smiles` stat and only ever sees the proposer's direct
  output, so fillers never pollute the gate rate (gate honesty is structural).
- **Threading** — `mutation_strategy` flows launch → `RunConfig` → `LoopState` (+ `CreateRunRequest`,
  `capychem-run`, `capychem-eval`); `create_run` drops the hardcode (`run.py:33`).
- **Provenance** — additive `ValidCandidate.proposer`; `Generation.proposer_used="mixed"` after a fallback.
- **Gate** — observational `valid_smiles_gate` helper, embedded in `summary_json` + printed by the CLI;
  never halts (FR-005 guarantees throughput).
- **Observability** — `llm:propose` Langfuse span (static call params; token/cost ride slice 05).
- **Testing** — TDD against the network-free `stub` backend; harness-free unit tests via monkeypatch
  (mirrors `test_eval_runner.py`); e2e LLM product run on stub (done-bar #1).

## Tasks

- [ ] T1 — `ValidCandidate.proposer` field + `validate` node tagging
- [ ] T2 — shared `loop/strategy.py` module
- [ ] T3 — thread `mutation_strategy` (config / state / API schema / CLIs)
- [ ] T4 — strategy-aware `propose` node + LLM span
- [ ] T5 — `fallback` node + topology + score merge + persist provenance
- [ ] T6 — observational >80% valid-SMILES gate (helper + summary + CLI verdict)
- [ ] T7 — headless `run_reproduction(mutation_strategy="llm")` + eval CLI flag
- [ ] T8 — e2e LLM product run on stub + full quality gate

## Notes

- **Stub-only.** Real DeepSeek `direct` run + the actual jnk3 ≥80% verdict + the beat verdict are slice 06.
- **Async/sync seam.** `propose_llm_sync` (= `asyncio.run`) bridges the async client into the synchronous
  headless eval path; safe because `capychem-eval` has no running loop.
- **No double-validation.** Fallback sizes its gap from the already-deduped `state["validated"]`.
- **Gotcha:** an existing `valid_smiles` exact-shape assertion may need the new `gate` key added (T6).
- **Deferred:** cost ledger / unique-call budget (s05), analyzer (m03), jnk3 launch + UI selector (s01),
  per-slot LLM retry, the Modal `propose()` `n=1` latent bug (no Modal access).
