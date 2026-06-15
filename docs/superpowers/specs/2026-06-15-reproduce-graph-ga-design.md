# Design — Slice `01-reproduce-graph-ga`

**Date:** 2026-06-15
**Status:** Design approved; pending written-spec review
**Milestone:** `01-harness-reproducibility` (SPEC §9 Phase 1)
**Related:** PRD G1 + NFR sample-efficiency · SPEC §6.2 (eval), §10 (testing) · `agent_docs/pmo-auc-and-baselines.md` (**BINDING** — source-verified PMO metric + Graph-GA baselines)

---

## 1. Problem & goal

The walking skeleton shipped a running loop but never built the canonical AUC-of-top-10 metric. `loop/logic.py` computes a "running curve" (survivor-pool top-10 mean per generation) and explicitly labels it *un-authoritative*, pointing at a not-yet-existent `packages/core/eval` as the future home of the real number.

This slice builds **`packages/core/capychem/eval/`** as the single source of truth for AUC-of-top-10-mean-vs-oracle-calls, plus a **`capychem-eval`** CLI, and **reproduces vanilla Graph-GA on QED to within ±0.02 of the published PMO number `0.940`** — proving the eval contract is trustworthy *before* any beat attempt (milestone 02). QED is a degenerate plumbing smoke test (oracle ceiling ~0.948, ±0.000 published std), chosen precisely because a broken pipeline lands unambiguously outside the band.

## 2. Design decisions (resolved during brainstorming)

| Fork | Decision | Why |
|---|---|---|
| AUC data source & where the unique-call budget lives | **Headless eval runner** — `eval/` owns a pure metric + a no-DB, memoized GA runner | Faithful PMO unique-call budget; fast & unit-testable; runs in CI without Postgres; product loop untouched (decouples from slice 3) |
| Product-loop memoization | **Defer to milestone 02** | Milestone 01 needs faithfulness only in the eval path; avoids editing shared loop files slice 3 also touches. *Flagged:* the product loop must adopt a unique-call budget for the G1 beat attempt |
| Full 10k reproduction run | **Run in-slice; record the number** | The ±0.02 exit criterion demands a real number in-band; recorded as evidence in the slice doc + handoff |
| PMO patience early-stop | **Implement it** (default 5, top-100 mean Δ<1e-3) | Cheap; it is how PMO reports its numbers; `finish=True` then pads the tail at the converged top-10 mean |

Rejected: **(B) reuse product loop + read DB rows** — requires Postgres for eval, slower, and the memoization change edits shared loop files slice 3 also touches. **(C) reuse loop + post-hoc dedup** — the loop wastes budget re-scoring duplicates, so the unique-call count won't match PMO and the AUC can fall outside ±0.02. Not faithful.

## 3. Architecture — new `packages/core/capychem/eval/`

- **`metric.py` — the one authoritative AUC.** Pure function
  `top_auc(buffer, top_n=10, finish=True, freq_log=100, max_oracle_calls=10000) -> float`,
  a line-for-line faithful port of PMO `main/optimizer.py`: chronological call-order replay, trapezoidal integration on the `freq_log` grid, the two tail terms (partial trapezoid + `finish` flat-pad), `÷ max_oracle_calls`. `buffer: dict[str, tuple[float, int]]` = `{smiles: (score, call_order)}` with `call_order` the 1-based first-seen ordinal. No I/O, no harness — pure and unit-testable.

- **`runner.py` — headless memoized GA reproduction runner.** Drives gen0→genN in-memory: **no Postgres, no LangGraph, no DB rows.** Holds the memoizing `mol_buffer`; a SMILES already in the buffer is **not** re-scored and does **not** advance the unique-call count. Stops on unique-call budget exhaustion or PMO patience. Returns `(mol_buffer, metadata)`. **Reuses existing primitives** — `oracle.propose_offspring`, `oracle.score_smiles`, `validate.validate_batch`, `loop.logic.merge_and_truncate` — so the GA algorithm is not duplicated; only the budget + persistence semantics differ from the product loop.

- **`baselines.py`** — the published Graph-GA per-task table from the reference note (at minimum `qed → 0.940`) + the `±0.02` reproduction tolerance, for the diff.

- **`cli.py`** — `capychem-eval` entrypoint. Registered in `packages/core/pyproject.toml` `[project.scripts]` as `capychem-eval = "capychem.eval.cli:main"`. (Slice 2 edits `[project.dependencies]` for `python-dotenv` — a different block, trivial merge.)

## 4. Faithfulness invariants (BINDING — from `agent_docs/pmo-auc-and-baselines.md`)

- `mutation_rate = 0.067` passed to the proposer (the `propose.py` `0.01` docstring example is **wrong**; a mismatch shifts AUC).
- `top_auc`: trapezoidal · `freq_log = 100` · `finish = True` · `÷ max_oracle_calls = 10000`.
- Budget counts **unique** (memoized) oracle calls; re-scoring a known SMILES does not advance the count.
- PMO Graph-GA defaults: `population_size = 120`, `offspring_size = 70`.
- Gen 0 scores the initial `population_size` molecules from `starting_pop.smi` (they consume unique calls, as in PMO).
- Per-gen seed `base_seed + gen_index` (existing proposer contract).
- Starting pop = CapyChem's shipped 200-SMILES subset, **not** PMO's ZINC-250K random-120 draw → expect "lands in the published band," **not** bit-identical. The ±0.02 tolerance absorbs starting-pop + single-vs-5-seed variance.

## 5. CLI contract & report

```
capychem-eval --task qed --budget 10000 --seed 42 \
  [--pop-size 120 --offspring 70 --mutation-rate 0.067]
```

Emits a JSON report: `{task, seed, budget, pop_size, offspring, mutation_rate, unique_calls_used, generations, auc_top10, baseline_published, tolerance, diff, within_tolerance, wall_seconds}`. `within_tolerance` is informational (only meaningful at full budget); the CLI does not hard-fail on it — the exit-criterion check is the recorded full-budget run.

**`--budget` feeds both the run's unique-call stop *and* the metric's `max_oracle_calls` normalizer.** Since PMO normalizes by `÷10000`, the published `0.940` is only reproduced at `--budget 10000`; a budget-200 smoke normalizes by 200, yielding a valid `[0,1]` number that is *not* comparable to `0.940` (machinery check only). The `top_auc` signature keeps `max_oracle_calls=10000` as its default purely for unit-test ergonomics.

## 6. Testing (SPEC §10)

- **Unit (load-bearing, no harness)** — `top_auc` against hand-computable synthetic buffers: constant top-10 mean → AUC equals that constant; a known ramp; `finish=True` tail-pad on an early-stopped buffer; the `freq_log` sampling grid. **This is where faithfulness is proven.**
- **Harness-backed smoke** — `capychem-eval --task qed --budget 200 --seed 42` runs end-to-end; report has `0 < auc < 1`, `unique_calls ≤ 200`. (Needs `CAPYCHEM_HARNESS_PYTHON`; in a worktree, point it at the main checkout's `harness/.venv`.)
- **Full reproduction (in-slice, recorded — NOT CI, per SPEC §10 "cost-bounded, on-demand")** — `--budget 10000`; AUC must land in **0.92–0.96**; the number is recorded in the slice doc + handoff as exit-criterion evidence. Local oracle backend (`CAPYCHEM_ORACLE_BACKEND` unset).

## 7. Risks

- **Wall-clock of the 10k repro** (~140+ generations × propose/score subprocess pairs, roughly 10–30 min local). Mitigation: fast budget=200 smoke in CI; the full run once, recorded.
- **Starting-pop divergence** from PMO → absorbed by ±0.02 (verified-reasonable in the reference note, tagged there as an engineering recommendation, not a PMO-published value).
- **Patience-stop correctness** could shift where `finish` padding begins → unit-test the runner's stop logic; for QED the converged ~0.94 plateau makes the band robust either way.
- **Second-AUC drift** — `eval/` is the sole authority; `loop/logic.py`'s running curve stays a live-UI estimate only. Do not let a second AUC definition appear.

## 8. Out of scope / deferred

- **Product-loop memoization / unique-call budget** → milestone 02 (required for the G1 beat attempt).
- **Higher-headroom task reproduction** (`jnk3`, `zaleplon_mpo`) + the first beat-Graph-GA attempt → milestone 02.
- **Full 23-task sweep** + CI baseline-diff wiring (SPEC §10) → milestone 03.
- **Langfuse end-to-end trace** → slice 2 (`02-langfuse-end-to-end`).
- **Valid-SMILES rate measurement** → slice 3 (`03-valid-smiles-measurement`); the >80% gate check rides with the LLM proposer in milestone 02.
