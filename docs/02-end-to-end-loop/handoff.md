# Handoff — 02-end-to-end-loop (slice 03 shipped — real-API smoke pending)

## Completed this session

- **Milestone 02 scoped** via an agent-team planning run (3 read-only dimension planners —
  agent-loop / backend / eval-web — + an adversarial verifier; 2 rounds; clean SIGN-OFF).
- Synthesized `docs/02-end-to-end-loop/milestone.md` + this handoff. User decisions locked:
  **task = jnk3**; **baseline = our own same-seed Graph-GA control**; **G6 honored for the LLM path**
  (pinned temp/seed + abstraction reachable from product loop *and* headless eval); **plateau-stop
  included** in m02 (the 6th slice).
- **Slice 03 `modal-llm-propose-endpoint` SHIPPED (code; real-API smoke pending):** brainstorm →
  design spec → implementation plan (6 TDD tasks) → slice doc → subagent-driven implementation (per-unit
  spec + code-quality reviews, all approved; final holistic review READY TO MERGE) → merged to `main`
  and **pushed to origin** (`5f50e03..09cbb0e`). Code commits `d6a4a41` · `d628b04` · `74a7246`
  (proposer.py adapter) · `5af173d` (worker `propose()`) · `09cbb0e` (ruff format). Planning docs
  `9f6977b` (spec) · `4d341e7` (plan + slice doc).
  - **Gate green (real output):** `pytest` 71 passed · `mypy` clean (29 files) · `ruff check` clean ·
    `ruff format` applied to the 2 new files (7 pre-existing unformatted files left untouched).
  - **Outstanding:** Task 6 (one-time real DeepSeek API smoke) — needs a `deepseek-api-key` Modal secret
    + `modal run apps/worker/app.py::propose_smoke`. The real path is NOT yet proven; CI runs the stub.
  - Decisions: wrap DeepSeek API in Modal (GPU swap designed-for); SMILES cleaning + cost modern-side.

## Slice status across milestone

- `01-launch-and-watch-jnk3` → planned
- `02-plateau-stop-and-signal` → planned
- `03-modal-llm-propose-endpoint` → shipped (code + stub-verified; real-API smoke pending) — frozen
- `04-llm-proposer-with-ga-fallback` → planned
- `05-unique-call-budget-and-cost-ledger` → planned
- `06-beat-graph-ga-on-jnk3` → planned

Build order: `01 ∥ 02 ∥ 03 → 04 → 05 → 06`.

## Current state

- `main` clean and **pushed to `origin/main`**. Slice 03 code lives in
  `packages/core/capychem/proposer.py` (+ `tests/test_proposer.py`) and `apps/worker/app.py` (`propose()`).
- Proposer has **three backends** via `CAPYCHEM_PROPOSER_BACKEND`: `stub` (default, deterministic,
  no network) · `modal` (DeepSeek via the worker) · `direct` (DeepSeek via local `httpx`, **no Modal** —
  added because Modal is unavailable). Other knobs: `CAPYCHEM_LLM_USD_PER_1K_IN`/`_OUT`, `CAPYCHEM_LLM_MODEL`
  (default `deepseek-v4-pro`). The real path needs a `DEEPSEEK_API_KEY` (operator key not yet created);
  Modal is NOT required.
- Carried infra (from milestone 01): Langfuse v2 on `:3001`, Postgres on `:5432`, `CAPYCHEM_ORACLE_BACKEND`
  unset (local harness). Eval authority is `packages/core/capychem/eval/`.

## Next session start here

Two threads, in priority order:
1. **Close slice 03's real-API smoke (Task 6, manual — Modal-free):** create a DeepSeek key at
   platform.deepseek.com, then `export DEEPSEEK_API_KEY=<key> CAPYCHEM_PROPOSER_BACKEND=direct` and call
   `propose_batch_async("Propose one drug-like SMILES. Output only the SMILES.", 2, temperature=0.7, seed=0)`
   (e.g. via `uv run python -c`). Confirm SMILES + token counts + cost return. If `deepseek-v4-pro` 404s,
   set `CAPYCHEM_LLM_MODEL` to a valid model; if DeepSeek rejects `n`/`seed`, adjust `_direct_propose`'s
   payload. This retires the integration risk and fully closes 03.
2. **Start slice 04 `llm-proposer-with-ga-fallback`** — the next critical-path slice (consumes the
   proposer adapter). Begin with brainstorm → spec → plan. Slices 01 and 02 are dependency-free and can
   slot in any time. A kickoff prompt for slice 04 is saved in the Obsidian vault (`prompts/`).

## Active concerns

- **Slice 04 is the heaviest** (abstraction + dual-reachability + LLM wiring + GA fallback + pinned
  determinism + valid-SMILES gate + spans). Watch its size during its session; if it exceeds 2 pages,
  reconsider splitting (the verifier endorsed keeping it whole for now).
- **Async/sync seam** (slice 04): async LLM client vs synchronous headless eval path — needs a sync
  bridge or sync client path for G6 reproducibility.
- **`valid_smiles {proposed, valid, rate}`** is a frozen contract (slice 04 reads, never reshapes).
- **Beat risk:** without the analyzer (m03), this is the MOLLEO-minus-analysis config; the LLM may not
  beat Graph-GA on jnk3. That IS the week-7 kill-switch — on failure, narrow scope, don't abandon.
- **`direct` backend hardening (deferred, non-blocking):** a malformed/error DeepSeek body (missing
  `choices`, or an HTTP error) currently surfaces a raw `KeyError`/httpx error rather than a clean
  `ProposerError`. Harden when slice 04/06 runs the real loop. Also: `deepseek-v4-pro` may not be a real
  model id — `CAPYCHEM_LLM_MODEL` is env-configurable; first real call confirms.
- **SPEC drift (note):** SPEC Alt D locked "Modal-served inference"; the `direct` backend is a conscious
  re-decision forced by no-Modal access. Modal remains the optional scaling path; revisit the SPEC line
  if Modal stays unavailable.
- **Doc hygiene (non-blocking):** SPEC §9 Phase 2 prose says "first ≥6/23 … on a single task" — treat
  as known-stale; m02's bar is ONE task.

## Slice log

- 2026-06-16 — Milestone 02 scoped (agent-team planning; 6 slices, clean verifier sign-off).
- 2026-06-17 — Slice 03 design spec + implementation plan + slice doc written (pre-code).
- 2026-06-18 — **Slice 03 shipped** (code; real-API smoke pending). Subagent-driven TDD, all reviews
  approved; `pytest` 71 passed; merged + pushed `5f50e03..09cbb0e`.
- 2026-06-19 — **Slice 03 follow-up:** added Modal-free `direct` DeepSeek backend (Modal unavailable);
  `pytest` 73 passed, reviewed READY TO MERGE; commit `90d2b9c`. Real path now runs without Modal.
