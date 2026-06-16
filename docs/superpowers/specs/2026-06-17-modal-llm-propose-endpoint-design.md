# Design — Modal `llm.propose` endpoint (milestone-02 slice 03)

**Status:** Approved
**Date:** 2026-06-17
**Milestone:** 02 `end-to-end-loop` (SPEC Phase 2)
**Slice:** `03-modal-llm-propose-endpoint` (build order: leads the milestone; deps: none)
**Consumed by:** slice 04 `llm-proposer-with-ga-fallback`

## Context & goal

Slice 03 stands up the **proposer-serving half** of milestone 02: a net-new Modal `propose`
function (DeepSeek-v4-pro) plus a modern async client adapter that returns proposed SMILES +
per-call token/cost, landing **alongside** the existing oracle `score()` in `apps/worker`. It
leads the milestone to **front-load the Modal+LLM integration risk**; slice 04 wires the result
into the loop's `propose` node behind a Proposer abstraction.

This design **mirrors the proven oracle pattern** (`apps/worker/app.py::score` + the env-selected
`oracle.py::score_batch_async`): the serving boundary returns raw model output + token counts, and
the modern adapter owns cost policy — exactly how `score()` returns `wall_ms` while `oracle.py`
computes USD.

## Key decisions

1. **Serving mechanism — wrap DeepSeek's API in Modal** (not self-hosted GPU weights). A lightweight
   Modal function calls DeepSeek's OpenAI-compatible chat-completions API; Modal still owns the
   endpoint, batching, retries, and per-call cost accounting. Fits the <$50/run cost gate and the
   week-7 timeline. SPEC Alt D leaned toward self-hosted Modal inference; this is a conscious
   re-decision driven by the cost gate + timeline + the milestone's "designed-for-expensive,
   shown-on-cheap" philosophy. **The adapter contract is identical to a future GPU backend**, so
   self-hosting can swap in later behind the same interface without touching callers.
2. **Done bar — prove the real path once.** Ship the adapter + a deterministic stub backend (CI runs
   on the stub, no network), AND deploy the Modal function and smoke-test it against the **real**
   DeepSeek API once, manually — retiring the integration risk that motivated sequencing this slice
   first.

## Components

### Modal worker — `apps/worker/app.py`
Add a `propose()` Modal function beside `score()`:
- **In:** `prompt: str`, `n: int` (batch size), `temperature: float`, `seed: int`, `model: str`.
- **Out:** `[{raw, smiles, tokens_in, tokens_out}]` — the raw completion, a best-effort extracted
  candidate string, and token usage. **No USD** (cost policy lives modern-side).
- Reads the DeepSeek API key from a **Modal secret** (never committed; env / secret store only).

### Modern adapter — `packages/core/capychem/proposer.py` (new module)
A separate module from `oracle.py` (distinct responsibility — talk to the proposer model — keeps each
unit focused and independently testable).
- `ProposalResult` dataclass: `raw: str`, `smiles: str` (best-effort cleaned candidate string),
  `tokens_in: int`, `tokens_out: int`, `cost_usd: float`.
- `propose_batch_async(prompt, n, *, temperature, seed) -> list[ProposalResult]`, env-selected
  backend:
  - **`stub`** (default; no network): deterministic seeded canned SMILES, `cost_usd=0`. Powers CI and
    lets slice 04 develop against a stable contract.
  - **`modal`**: awaits the worker `propose`; `cost_usd = tokens_in×in_rate + tokens_out×out_rate`.
- Env keys (mirroring `CAPYCHEM_ORACLE_*`): `CAPYCHEM_PROPOSER_BACKEND` (`stub`|`modal`),
  `CAPYCHEM_LLM_USD_PER_1K_IN` / `CAPYCHEM_LLM_USD_PER_1K_OUT` (placeholder rates — **not a price
  guarantee, PRD N6**), `CAPYCHEM_LLM_MODEL`.
- Lazy `import modal` only on the modal path (the `stub` backend never imports modal — mirrors
  `oracle.py`).

## Contract boundary (the seam with slice 04)

The adapter returns the model's **cleaned proposed string** (strip code fences / whitespace) — it does
**not** RDKit-validate. Validation stays in the loop's `validate` node (slice 04); invalid strings
there trigger the Graph-GA fallback (FR-005). `temperature` + `seed` are first-class params so slice 04
can pin them for G6 reproducibility. So `ProposalResult.smiles` means "the model's proposed string,
cleaned," not "a verified molecule."

## Data flow

```
slice 04 caller
  → proposer.propose_batch_async(prompt, n, temperature, seed)
      → [ stub  (deterministic, no network) | modal → DeepSeek API ]
  → list[ProposalResult]
  → slice 04 feeds .smiles into the existing `validate` node (RDKit; invalid → Graph-GA fallback)
  → slice 05 sums .cost_usd into RunCost.llm_cost_usd
```
Slice 03 only **produces** the result + cost; it persists nothing and touches no loop/cost code.

## Error handling

- API failure / timeout / malformed response → typed `ProposerError` (mirrors `HarnessError`), with a
  truncated payload in the message.
- Unknown / unset backend → `ValueError` listing valid options (mirrors `oracle.py`).
- Missing DeepSeek key on the modal path → a clear "set the Modal secret" error.
- Fallback-on-error **policy** is slice 04's call (the FR-005 Graph-GA fallback also covers a failed
  batch); slice 03 just surfaces a clean typed error.

## Testing

**Unit (CI, no network):**
- Stub determinism: same `seed` → same output; `cost_usd == 0`; returns exactly `n` results.
- Modal path with a **monkeypatched Modal function** (pattern: `test_oracle_backend.py`): asserts
  `cost_usd` computed from token counts and the configured rates; a malformed row → `ProposerError`.
- SMILES extraction (code-fence / whitespace stripping).
- Backend selector + env-rate parsing.

**Manual, one-time (retires the integration risk — the done bar):**
- DeepSeek key → Modal secret; `modal deploy apps/worker/app.py` (or a `propose` smoke entrypoint);
  call `propose` against the real API; confirm SMILES + token counts return and `cost_usd` computes.
- Secrets via the Modal secret store / env only — **never committed** (critical constraint).

## Out of scope (this slice)

- Prompt construction (slice 04).
- RDKit validation (the `validate` node, slice 04).
- `RunCost.llm_cost_usd` population / the cost-gate rewire (slice 05) — slice 03 only *returns*
  `cost_usd`.
- The Proposer abstraction + `mutation_strategy` threading (slice 04).
- GPU self-hosting (designed-for via the stable contract, not built).

## Notes / open items for the plan

- Exact DeepSeek model id is left to `CAPYCHEM_LLM_MODEL` (env-configurable) rather than hardcoded.
- Which HTTP/SDK client the Modal `propose` uses (OpenAI-compatible SDK vs raw `requests`) is a
  plan-level detail — the worker image already declares `requests`.
