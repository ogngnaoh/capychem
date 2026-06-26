# Design — Beat Graph-GA on jnk3 (milestone 02, slice 06)

**Date:** 2026-06-26
**Slice:** `06-beat-graph-ga-on-jnk3`
**Milestone:** `02-end-to-end-loop` (SPEC Phase 2) — the finale slice
**Deps:** slices 01, 04, 05 (shipped + frozen)
**Status:** approved (design); pre-implementation

## Problem

Milestone 02's week-7 kill-switch asks one question: does the LLM-proposer loop
beat vanilla Graph-GA on jnk3, by AUC-of-top-10, under the 10k unique-oracle-call
budget? Everything to *run* both strategies exists — the headless eval runner
(`packages/core/capychem/eval/runner.py`) drives `mutation_strategy ∈ {graph_ga,
llm}` through the same memoized path and feeds the canonical `top_auc`
(`eval/metric.py`). What is missing is the head-to-head: a reproducible way to run
both same-seed, measure both, surface the LLM validity gate, and render the
verdict. Plus one carried correctness blocker must be cleared first.

Three concrete gaps:

1. **Gate-purity BLOCKER (product loop).** `summary_json.valid_smiles.rate`
   accumulates the gen-0 `"starting"` seed population (always RDKit-valid), so it
   is *not* the LLM proposer's validity rate. The >80% gate (milestone-02 exit
   criterion 2) reads this; on a real run it dilutes the kill-switch signal.
   (Carried from slice-04 final review; milestone.md:93-98.)
2. **No validity surfaced headless.** `run_reproduction` returns only
   `mol_buffer / generations / unique_calls` — the verdict run cannot report the
   LLM valid-SMILES rate without a separate Postgres-backed product run.
3. **No head-to-head + no jnk3 baseline.** `GRAPH_GA_AUC_TOP10` has only `qed`;
   there is no single command that runs both strategies same-seed and emits a
   comparison + verdict.

This slice clears the blocker, surfaces LLM-only validity in the headless path,
registers the jnk3 published baseline as a sanity reference, adds a head-to-head
verdict layer, and uses it to produce the kill-switch call on jnk3 — via a
**staged run** (small calibration run first, then an explicit go/no-go on the
full 10k run).

## Goals

1. `summary_json.valid_smiles.rate` (product loop) counts the **LLM proposer
   only** — the fix excludes the gen-0 seed pop and any non-LLM batches; the
   `graph_ga` fallback fills are already outside the stats path (see §2). Semantic:
   pure-LLM validity, the thing the >80% gate is about.
2. The headless eval runner surfaces the same LLM-only validity rate, so the
   verdict run is self-contained and reproducible (G6).
3. A `--head-to-head` mode runs `llm` + `graph_ga` same-seed on a task, measures
   both via the canonical `top_auc`, and emits both AUCs, the diff, the LLM
   valid-rate + gate, and `beat = llm_auc > ga_auc`.
4. jnk3's published Graph-GA AUC (0.553) is registered as a *sanity reference*
   (the head-to-head decision still uses our own same-seed control, not the
   published number).
5. A staged real run on jnk3 produces a directional verdict + cost/wall-time
   calibration; the authoritative full-10k run is a separate, explicit decision.

Goals 1-4 are code (deterministic, stub-testable, no real spend). Goal 5 is the
experiment. These map to milestone-02 exit criteria 2 (>80% gate, now honest) and
8 (the beat verdict via the canonical eval module, reproducible to ±1%).

## Non-goals (explicitly deferred)

- **Analyzer step + `AnalyzerHypothesis`** — the differentiator, milestone 03.
- **Full 23-task PMO sweep + multi-task UI** — milestone 03. This slice proves the
  bar on the ONE task jnk3.
- **Compare-runs view** — milestone 04.
- **Expensive oracles, multi-objective** — stretch / out of milestone.
- **A product-loop / Postgres-backed run for the verdict.** The verdict is
  headless (deterministic, DB-free, G6). The product-loop gate-purity fix (goal 1)
  is still done — it keeps the live watch-live `summary_json` honest — but the
  *verdict numbers* come from the headless path.
- **Plateau-stop (slice 02).** Independent; not part of this slice. The headless
  runner already has its own PMO patience stop.
- **Auto-running the full 10k experiment.** Staged: small run, then human go/no-go.

## Key decisions (resolved in brainstorming)

- **Gate semantic = pure-LLM.** Count only generations whose proposer is the LLM
  (`_proposer == "llm"`), so the gen-0 `"starting"` seed pop and (on a
  graph_ga-strategy run) the GA batches are excluded. The gate measures how often
  the *LLM* emits valid SMILES. Note: the `graph_ga` **fallback fills** are already
  structurally excluded — they are produced in the `fallback` node *after* the
  `validate` node that accumulates `_validation_stats`, so they never enter the
  stats. The fix therefore reduces to one guard, not a multi-source filter.
  (Rejected: exclude only the seed — would also keep GA batches on a graph_ga run.)
- **Headless validity tracking (goal 2) is in scope.** The verdict is then one
  self-contained reproducible command, instead of requiring a separate DB-backed
  product run just to read the gate number. (Rejected: skip it, read the gate
  from a product run — more moving parts, not reproducible same-seed.)
- **Head-to-head uses our own same-seed control, not the published 0.553.** The
  published number is a sanity reference only (a wildly-off control AUC flags a
  broken pipeline). This is the milestone's explicit instruction (milestone.md:34).
- **Staged execution.** Small calibration run (~1500 unique calls, seed 42) →
  review directional verdict + cost/wall-time → explicit decision on the full 10k.
- **One CLI entry point.** Extend `capychem-eval` with `--head-to-head` rather than
  add a second console script.

## Design

### 1. LLM-only validity — shared semantic, two surfaces

The pure-LLM validity rate = (count of valid LLM proposals) / (count of LLM
proposals), per generation, summed across generations ≥1, **before** the
`graph_ga` fallback fills and **excluding** the gen-0 seed pop.

**Headless** (`packages/core/capychem/eval/runner.py`): the llm branch today calls
`valid_llm = validate_batch([(r.smiles, None) for r in results])` (runner.py:84)
*before* `fallback_fill` (runner.py:85). Swap that one call for
`validate_batch_with_stats(...)` — it returns the *same* deduped
`list[ValidCandidate]` plus a `ValidationStats(proposed, valid)`. Crucially,
`ValidationStats.valid` is the **pre-dedup** RDKit-valid count (validate.py:33-47:
"validity, not novelty"), so the headless rate definition is byte-identical to the
product loop's. Accumulate `proposed += stats.proposed`, `valid += stats.valid`
across generations ≥1; the gen-0 seed block (runner.py:68-73) never touches them.

- Extend `ReproResult` with `llm_proposed: int`, `llm_valid: int`,
  `valid_rate: float | None` (None on a `graph_ga` run — no LLM proposals).
- A `graph_ga` run leaves both counters 0 → `valid_rate = None`.
- `validate_batch` and `validate_batch_with_stats` produce identical
  `list[ValidCandidate]` (the former wraps the latter), so `fallback_fill` is
  unaffected by the swap.

**Product loop** (the BLOCKER, `loop/graph.py`): today the `validate` node
(graph.py:90-106) accumulates `_validation_stats` from `state["proposed"]` for
*every* generation — including gen-0, whose `_proposer` is `"starting"` and whose
seeds are always RDKit-valid. That is the only contaminant: the fallback fills
enter via the separate `fallback` node *after* `validate`, so they are not in the
stats. The fix is a one-line guard at the exact point `proposer_label` is already
read (graph.py:97-98):

```python
validated, stats = validate_batch_with_stats(state["proposed"])
proposer_label = state.get("_proposer", "graph_ga")
validated = [replace(vc, proposer=proposer_label) for vc in validated]
out = {"validated": validated}
if proposer_label == "llm":                      # gen-0 "starting" + GA batches skipped
    prev = state.get("_validation_stats", {"proposed": 0, "valid": 0})
    out["_validation_stats"] = {
        "proposed": prev["proposed"] + stats.proposed,
        "valid":    prev["valid"]    + stats.valid,
    }
return out
```

- For an **llm-strategy** run: gen-0 (`"starting"`) is skipped; gen-1+ (`"llm"`)
  accumulate pure-LLM proposed/valid. `_proposer` is still `"llm"` in the validate
  node — the `fallback` node only flips it to `"mixed"` afterward (graph.py:128).
- For a **non-LLM** run (graph_ga, or any run that never proposes via the LLM):
  `_validation_stats` is **never written** → stays `None` → `build_summary`
  (`logic.py:87`) **omits** the `valid_smiles` block entirely. This is the
  intended behavior: the >80% gate is an LLM-validity concept; a graph_ga run has
  no LLM validity to report, so reporting `rate: 0.0` (looks like "0% valid") would
  be *more* misleading than omitting it. Today such a run reports an inflated
  ~100% block (seed pop) — removing it is the correction.
- `build_summary` and `logic.py` are **unchanged**; the frozen `valid_smiles`
  block shape (`{proposed, valid, rate, gate}`, read by slice 04, milestone.md:88)
  is preserved for the case where the block is present.

> **Consumer-check (planning must verify):** slice 01's shipped jnk3 launch runs
> the *graph_ga* default, so a product graph_ga run's `summary_json` will lose its
> `valid_smiles` block. Confirm (a) the web watch-live/run-detail consumer treats
> `valid_smiles` as optional (absent → hide, not crash), and (b) `test_loop_valid_smiles.py`
> and any other test asserting a block on a non-llm run is updated to the corrected
> semantic. If a consumer hard-requires the block, fall back to emitting it with
> `proposed==valid==0` and document the `rate: 0.0` meaning — but omission is preferred.

### 2. Head-to-head verdict layer

New `packages/core/capychem/eval/beat.py`:

```python
@dataclass(frozen=True)
class BeatVerdict:
    task: str
    seed: int
    budget: int
    llm_auc: float
    graph_ga_auc: float
    diff: float                 # llm_auc - graph_ga_auc
    beat: bool                  # llm_auc > graph_ga_auc
    llm_valid_rate: float | None
    llm_valid_gate: dict        # valid_smiles_gate(rate)
    published_baseline: float | None   # sanity reference, if registered
    llm_unique_calls: int
    graph_ga_unique_calls: int

def run_head_to_head(task, budget, seed, *, pop_size=120, offspring=70,
                     mutation_rate=0.067) -> BeatVerdict:
    ga  = run_reproduction(task, budget, seed, ..., mutation_strategy="graph_ga")
    llm = run_reproduction(task, budget, seed, ..., mutation_strategy="llm")
    ga_auc  = top_auc(ga.mol_buffer,  top_n=10, max_oracle_calls=budget)
    llm_auc = top_auc(llm.mol_buffer, top_n=10, max_oracle_calls=budget)
    ... assemble BeatVerdict (llm_valid_rate from llm.valid_rate;
        gate from valid_smiles_gate; published_baseline from GRAPH_GA_AUC_TOP10)
```

- Same `seed` passed to both runs (G6). Both AUCs via the canonical `top_auc` —
  no ad-hoc AUC recomputation (CLAUDE.md gotcha).
- `published_baseline` is looked up but never gates `beat`; it rides in the report
  as a sanity check.

### 3. jnk3 baseline registration

`packages/core/capychem/eval/baselines.py` — add `"jnk3": 0.553` to
`GRAPH_GA_AUC_TOP10` (source: `agent_docs/pmo-auc-and-baselines.md`, NeurIPS 2022
Table 2, mean over 5 seeds). Comment notes it is a *single-vs-5-seed* reference;
the `DEFAULT_TOLERANCE` (0.02) is for the qed reproduction smoke and is **not**
applied to the head-to-head decision (our control is the comparator, not 0.553).

### 4. CLI — `--head-to-head`

`packages/core/capychem/eval/cli.py`:

- Add `--head-to-head` (store_true). When set, ignore `--mutation-strategy`, call
  `run_head_to_head(...)`, and emit a `BeatVerdict`-shaped JSON report (task, seed,
  budget, both AUCs, diff, beat, llm_valid_rate + gate, published_baseline, both
  unique-call counts, wall_seconds). When unset, behavior is unchanged (today's
  single-strategy report).
- The report is the slice's machine-readable verdict; a human verdict summary is
  written into the slice doc + (for the full run) committed.

### 5. Staged run protocol (the experiment)

Real DeepSeek via the `direct` backend (`.env.local`: `CAPYCHEM_PROPOSER_BACKEND=
direct`, `CAPYCHEM_LLM_MODEL=deepseek-v4-pro`, `DEEPSEEK_API_KEY`). The eval CLI
reads process env — the run command must export `.env.local` first (the CLI does
not auto-load it).

1. **Calibration run** — `--head-to-head --task jnk3 --budget 1500 --seed 42`.
   Capture: both AUCs, diff, LLM valid-rate, total wall-time + per-generation
   wall-time (the jnk3 per-batch model-reload perf concern), and DeepSeek cost
   (expected « $1 at this budget). JSON → scratchpad (calibration, throwaway).
2. **Review together** — directional verdict + measured cost/time. Decide whether
   to commit to the full 10k run (a second explicit go/no-go).
3. **(On go) Full run** — `--budget 10000 --seed 42`. Its JSON report + a written
   verdict are committed as the week-7 kill-switch evidence.

Verdict reading (both stages): `beat == True` → passes the week-7 kill-switch (on
track for milestone 03). `beat == False` → narrow scope per the kill-switch
(milestone.md:35) — **do not abandon**; the analyzer-only narrative remains.

## Testing (TDD — a failing test precedes each change)

`packages/core/tests/`:

- **Headless validity (new, `test_eval_runner.py`):** an llm run whose stub
  proposer emits a known mix of valid/invalid SMILES → `ReproResult.llm_proposed
  / llm_valid / valid_rate` reflect LLM-only counts; a `graph_ga` run →
  `valid_rate is None`.
- **Head-to-head (new, `test_eval_beat.py`):** stub LLM, tiny budget → `BeatVerdict`
  shape, `beat == (llm_auc > graph_ga_auc)`, `diff` sign, same-seed determinism
  (two calls → identical verdict), published_baseline populated for jnk3.
- **Gate purity (`test_loop_valid_smiles.py`):** an llm-strategy product run whose
  LLM batch has a known invalid fraction (gen-0 seeds always valid) →
  `summary_json.valid_smiles` reflects the **LLM-only** pre-dedup rate (gen-0
  excluded; fallback fills are structurally absent from `_validation_stats`). A
  graph_ga-strategy run → **no** `valid_smiles` block in `summary_json`. Update any
  existing assertion that expects a block on a non-llm run.
- **CLI (`test_eval_cli.py`):** `--head-to-head` emits the verdict-shaped report;
  the existing single-strategy report path is unchanged.
- **Baseline (`test_eval_baselines.py`):** `compare_to_baseline("jnk3", ...)`
  resolves; jnk3 present in `GRAPH_GA_AUC_TOP10`.

No real DeepSeek spend in any test (stub backend). Gate green before merge:
`uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .`
· `uv run ruff format .` (web suite untouched — no web changes this slice).

## Files touched

- `packages/core/capychem/eval/runner.py` — `ReproResult` validity fields; LLM
  proposed/valid counters in the llm branch.
- `packages/core/capychem/eval/beat.py` — **new**: `BeatVerdict`,
  `run_head_to_head`.
- `packages/core/capychem/eval/baselines.py` — register `"jnk3": 0.553`.
- `packages/core/capychem/eval/cli.py` — `--head-to-head` mode + verdict report.
- `packages/core/capychem/loop/graph.py` — one-guard fix: accumulate
  `_validation_stats` only when `_proposer == "llm"` (gate-purity BLOCKER).
- Tests under `packages/core/tests/` (new + updated as above).
- `docs/02-end-to-end-loop/06-beat-graph-ga-on-jnk3.md` — slice doc (results +
  full-run command); written during execution, frozen on ship.

Untouched: `loop/logic.py` (`build_summary` unchanged — shape preserved),
`apps/web/*` (no UI change; the consumer-check above only *verifies* it tolerates
an absent block), `apps/worker/*` (no Modal change — direct backend), `proposer.py`,
`oracle.py`, `validate.py`, `db/models.py` (no migration), `harness/` (never
imported).
