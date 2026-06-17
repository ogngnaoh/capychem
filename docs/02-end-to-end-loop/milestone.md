# Milestone 02 — end-to-end-loop

> SPEC Phase 2. Single source of truth for this milestone. Synthesized 2026-06-16 via an agent-team
> planning run (3 dimension planners + an adversarial verifier, 2 rounds, clean sign-off).

## Goal

Run the full propose→score→redesign loop with an **LLM proposer (Graph-GA fallback)** on **jnk3**,
beating vanilla Graph-GA on it by AUC-of-top-10 under the 10k **unique**-oracle-call budget, at
**<~$50/run**, with launch + watch-live working for it.

## Scope

- **LLM proposer + a Proposer abstraction** so the LLM and the existing Graph-GA proposer coexist,
  selected via the existing `Run.mutation_strategy` column (FR-004). The abstraction is reachable from
  **both** the product loop and the headless eval harness (so G6 reproducibility holds for the LLM
  path; LLM temperature/seed pinned).
- **Net-new Modal `llm.propose` endpoint** (DeepSeek-v4-pro) + a modern async client adapter, landing
  alongside the existing oracle `score()` in `apps/worker`. Cold-start tolerated by the existing WS
  heartbeat.
- **LLM→Graph-GA invalid-output fallback** so generation throughput never drops on invalid SMILES
  (FR-005); wraps the existing `oracle.propose_offspring` seam.
- **The >80% valid-SMILES gate check** against the LLM proposer (reads the frozen
  `summary_json.valid_smiles.rate`).
- **Backend cost/budget layer — "designed-for-expensive, shown-on-cheap":** memoization / unique-
  oracle-call budget (repeats hit a cache; budget counts unique calls) + populate `RunCost.llm_cost_usd`
  so `total_usd` sums llm+oracle and the existing $50 gate fires on LLM spend alone. Built to the shape
  expensive oracles will need, but **demonstrated only on the cheap CPU jnk3 oracle** — no expensive
  oracle added.
- **FR-003 plateau-stop + live plateau signal** (Story 2): `stop_reason()` checks the already-plumbed
  `plateau_window`; a `plateaued` status; the signal surfaced in watch-live.
- **jnk3 launch + watch-live** (minimal — the single chosen task, not a multi-task selector).
- **First beat-Graph-GA attempt on jnk3** via the canonical `packages/core/capychem/eval` module,
  measured against **our own same-seed Graph-GA control** on jnk3 (not a published number). This is the
  week-7 kill-switch: can't beat on jnk3 → narrow scope.
- **LLM-call generation spans** in Langfuse.

## Non-goals

1. **Analyzer step + `AnalyzerHypothesis` entity** — the differentiator; deferred to milestone 03.
2. **Full 23-task PMO sweep + multi-task UI selector** — milestone 03. This milestone proves the bar on
   ONE task; the ≥6/23 figure is the G1 target (due 2026-09-15) and ≥3/23 is the m03 week-8 bar.
3. **Compare-runs view** — milestone 04.
4. **Expensive oracles (ADMET-AI / Vina / DiffDock)** — stretch. The backend is *architected* for them
   but exercised only on cheap CPU oracles this milestone.
5. **Multi-objective optimization** — PMO single-objective only.

## Slices

Build order: `01 ∥ 02 ∥ 03 → 04 → 05 → 06`. Each is an independently shippable vertical slice; per-slice
docs (`NN-<slice>.md`) are written when that slice's work starts.

01. `launch-and-watch-jnk3` — register jnk3 as a launchable + watch-live target on the existing
    Graph-GA loop. *(planned)* — deps: none
02. `plateau-stop-and-signal` — enforce FR-003 plateau stop and surface the live plateau signal
    (Story 2). *(planned)* — deps: none
03. `modal-llm-propose-endpoint` — net-new Modal `llm.propose` (DeepSeek-v4-pro) + async client
    adapter returning SMILES + token/cost. *(in-progress — spec + plan written)* — deps: none
04. `llm-proposer-with-ga-fallback` — Proposer abstraction selected via `mutation_strategy` (reachable
    from product loop + headless eval), LLM proposer wired into the propose node with Graph-GA fallback,
    pinned determinism, the >80% valid-SMILES gate check, LLM-call spans. *(planned)* — deps: 03
05. `unique-call-budget-and-cost-ledger` — memoize/dedup oracle calls by canonical SMILES so budget
    counts unique calls; populate `llm_cost_usd`; rewire the per-gen cost gate to read `total_usd`.
    *(planned)* — deps: 03, 04
06. `beat-graph-ga-on-jnk3` — run the LLM-proposer loop on jnk3 to budget; run vanilla Graph-GA on
    jnk3 same-seed as the head-to-head control; measure both via the canonical eval module (headless);
    render the week-7 kill-switch verdict. *(planned)* — deps: 01, 04, 05

## Integration notes

- **Proposer abstraction.** `loop/graph.py`'s `propose` node hardcodes Graph-GA (`oracle.propose_offspring`).
  Slice 04 introduces the abstraction selected by `Run.mutation_strategy` (today hardcoded `"graph_ga"`
  in `run.py:33`, absent from `RunConfig`/`LoopState` — slice 04 threads it launch→`RunConfig`→`LoopState`).
  Place it so both the `apps/api` product runner and `packages/core/capychem/eval/runner.py` can select
  it (G6).
- **Modal.** `apps/worker/app.py` gains `llm.propose` alongside `score()`; the client adapter mirrors
  `oracle.py`'s `score_batch_async(modal)` path. Never import from `harness/` — subprocess+JSON only.
- **Cost / budget.** `cost.record_oracle_cost` already sums llm+oracle into `total_usd`; `RunCost.llm_cost_usd`
  column already exists (no migration). Slice 05 adds memoization keyed on canonical SMILES
  (`validate.py` already canonicalizes) so `calls_used` (`graph.py:97`) counts unique calls, populates
  `llm_cost_usd`, and rewires the per-gen gate (`apps/api .../runner.py` ~199-201) to read `total_usd`.
- **Plateau.** Slice 02's `stop_reason()` (`loop/logic.py`) check uses the per-gen top-10-mean history
  already in `LoopState.auc_curve`; emits a `plateaued` status + a WS event + a `LiveRun.tsx` signal.
  Light watch-live overlap with slice 01 — coordinate (not a cycle).
- **Eval.** Slice 06 uses `eval` (`metric.top_auc`; `run_reproduction` is task-agnostic) for both the
  LLM run buffer and the jnk3 Graph-GA control — do not recompute AUC ad hoc.
- **Frozen contract.** `valid_smiles {proposed, valid, rate}` is read by slice 04, never reshaped.
- **Async/sync seam (impl note for slice 04).** The LLM client is async (`.aio`/`score_batch_async`)
  while the headless eval path (`run_reproduction`/`score_smiles`) is synchronous — slice 04 needs a
  sync bridge (e.g. `asyncio.run`) or a sync client path to host the async proposer headless.

## Exit criteria

1. A run with `mutation_strategy="llm"` on jnk3 completes the full propose→validate→score→persist→
   stop_check loop end-to-end within the 10k **unique**-oracle-call budget.
2. The LLM proposer's `summary_json.valid_smiles.rate` is measured on jnk3; ≥80% passes the gate
   (below → re-examine prompt/model before scaling).
3. Invalid LLM output is backfilled by the Graph-GA fallback — no generation is starved.
4. Budget counts **unique** oracle calls (repeats memoized, not re-scored or re-counted).
5. `RunCost.total_usd` sums llm + oracle; the $50 gate fires on LLM spend alone with the cheap jnk3
   oracle.
6. Plateau stop is enforced and the plateau signal is surfaced in watch-live.
7. jnk3 is launchable and watchable live from the web.
8. The beat verdict — LLM AUC-of-top-10 vs our own same-seed Graph-GA control on jnk3, both via the
   canonical eval module (headless), reproducible to ±1% (G6) — is produced. Beating Graph-GA on jnk3
   passes the week-7 kill-switch; not beating → narrow scope (do not abandon).
