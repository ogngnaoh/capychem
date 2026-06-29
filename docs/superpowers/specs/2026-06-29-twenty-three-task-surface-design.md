# Design — Twenty-three-task surface (milestone-03 slice 04)

**Status:** Approved
**Date:** 2026-06-29
**Milestone:** 03 `analyzer-and-scale` (SPEC Phase 3 — the differentiator)
**Slice:** `04-twenty-three-task-surface` (build order: `01 → {02 ∥ 03 ∥ 04} → 06 → 05`; deps: none)
**Consumes:** `eval/baselines.py`, `eval/runner.py`, `eval/beat.py`, `eval/verdict.py`, `eval/metric.py`,
`eval/cli.py` (milestone-02/03 eval stack), `apps/api/.../schemas.py`, `apps/web/app/page.tsx` — all stable.
**Consumed by:** slice 05 (`week-8-sweep-and-gate` — runs `--all --analyzer-verdict`, the Week-8 bar).

## Context & goal

Today the project is wired for **two** PMO tasks (`qed`, `jnk3`): the API schema allow-lists exactly those,
the launch UI hardcodes `jnk3`, and `eval/baselines.py` registers only their published Graph-GA numbers. The
Week-8 bar (slice 05) needs the **full 23-task PMO surface** — every task launchable and a sweep runner that
walks all 23.

This slice is **pure plumbing, no eval cost**: a single source-of-truth task registry, the 23 published
Graph-GA baselines (from the verified `agent_docs/pmo-auc-and-baselines.md` table), the schema + UI widened to
all 23, and a **mode-pluggable** `capychem-eval --all` sweep runner. It does **not** run the real sweep (slice
05, cost-bounded, confirm-before-invoke) and adds **no** analyzer/proposer/oracle behavior — the harness
`Oracle(name=task)` is already task-agnostic (verified in `harness/capychem_harness/score.py`), so there is
**no harness change**.

One design decision confirmed at brainstorm:
- **Mode-pluggable `--all`.** `--all` composes with the existing mode flags rather than being purpose-built for
  one verdict. `--all` alone = graph_ga reproduction across 23 vs published baselines (cheap, no LLM);
  `--all --head-to-head` = llm-vs-graph_ga across 23; `--all --analyzer-verdict` = slice 05's
  with-vs-without across 23. One runner, mode-agnostic — slice 05 becomes a flag-flip + a real run.

## Key decisions

1. **Single source of truth = `eval/tasks.py::PMO_TASKS`.** A new module holds the 23 canonical PyTDC oracle
   names as a `tuple[str, ...]` in PMO Table 2 order. `eval/baselines.py` and the API schema both derive
   their allow-list from it; the sweep defaults to iterating it. Placement in `eval/` (not a new top-level
   module) because the registry is an eval-surface concept and `baselines.py` — its primary consumer — already
   lives there; `apps/api` already imports from `capychem`, so the schema can reference it without a new dep.
   - *Rejected — duplicate the 23 names in schema + baselines + sweep:* three lists drift; the milestone
     explicitly asks for a "canonical task registry."

2. **Schema validates against the registry via a `field_validator`, not a 23-value `Literal`.** `schemas.py`
   becomes `task: str = "qed"` + `@field_validator("task")` that raises (→ 422, preserving FR-015) when the
   value is not in `PMO_TASKS`. A field-validator keeps a single source of truth (the registry) and avoids a
   23-arm `Literal` that would itself duplicate the list.
   - **Consequence (must handle):** `drd2` — used as the "unknown task" in `test_task_surface.py` — is a real
     PMO task and becomes **valid**. That test must switch to a genuinely non-PMO name (e.g. `not_a_real_task`).
   - *Trade-off accepted:* OpenAPI no longer enumerates the 23 in the schema. Acceptable — the UI owns task
     discovery; a `GET /tasks` endpoint is out of scope (decision 4).

3. **The sweep is a separate, testable module `eval/sweep.py`; `cli.py` only wires the flag.** Mirrors the
   established pattern (`beat.py`, `verdict.py` hold logic; `cli.py` wires flags → reports). `run_sweep`
   dispatches each task to the **existing** per-task primitive by mode — never a new AUC or comparator path:
   - `reproduce` → `run_reproduction` + `top_auc` + (`compare_to_baseline` when registered);
   - `head_to_head` → `run_head_to_head` (`BeatVerdict`);
   - `analyzer_verdict` → `run_analyzer_verdict` (`AnalyzerVerdict`).
   - *Rejected — inline the loop in `cli.py`:* untestable without argv plumbing; breaks the module/CLI split.

4. **UI lists the 23 from a static web-side const; no `GET /tasks` endpoint.** The PMO 23 are fixed forever, so
   a small `PMO_TASKS` const in the web (commented as mirroring the core registry) is simpler than a new
   endpoint + fetch + loading state. `app/page.tsx` gains a `<select>`, defaults to **jnk3** (the validated
   demo task with the proven analyzer win), retitles "Launch a jnk3 optimization" → "Launch an optimization",
   and threads the chosen `task` into `createRun` (currently hardcoded `"jnk3"`).
   - *Rejected — `GET /tasks` single-source endpoint:* YAGNI for a static 23-element list; adds an endpoint +
     async loading the slice doesn't need.

5. **Per-task error isolation in the sweep.** A 23-task sweep is long; one task throwing (e.g. an oracle
   model download hiccup) must record an error row and let the sweep continue — never abort the other 22. Each
   row is either a result or an `{task, error}` entry; the summary counts only successful rows.

## Components

### Task registry — `packages/core/capychem/eval/tasks.py` (new)
- `PMO_TASKS: tuple[str, ...]` — the 23 canonical PyTDC oracle names, in `agent_docs/pmo-auc-and-baselines.md`
  Table 2 row order (order is cosmetic — it only sets UI dropdown + sweep-row order, not correctness):
  `qed, zaleplon_mpo, perindopril_mpo, celecoxib_rediscovery, troglitazone_rediscovery, drd2, jnk3, gsk3b,
  albuterol_similarity, amlodipine_mpo, deco_hop, fexofenadine_mpo, isomers_c7h8n2o2, isomers_c9h10n2o2pf2cl,
  median1, median2, mestranol_similarity, osimertinib_mpo, ranolazine_mpo, scaffold_hop, sitagliptin_mpo,
  thiothixene_rediscovery, valsartan_smarts`.
- Module docstring cites `agent_docs/pmo-auc-and-baselines.md` as the source and notes every score is an
  in-silico oracle score (PRD N6).

### Baselines — `packages/core/capychem/eval/baselines.py` (extend)
- `GRAPH_GA_AUC_TOP10` gains all 23 entries from the verified table (qed 0.940 … valsartan_smarts 0.000;
  Sum 13.751). `compare_to_baseline` and `DEFAULT_TOLERANCE` are unchanged.
- Replace the jnk3-specific "SANITY REFERENCE only" comment with a general note: the published numbers are a
  single-vs-5-seed sanity reference; every head-to-head/verdict decision uses our **own same-seed control**,
  never the published number as the comparator.

### Schema — `apps/api/capychem/api/schemas.py` (modify)
- `CreateRunRequest.task: str = "qed"` + `field_validator("task")` → `ValueError` (→ 422) unless
  `task in PMO_TASKS`. Imports `PMO_TASKS` from `capychem.eval.tasks`.

### Sweep runner — `packages/core/capychem/eval/sweep.py` (new)
- `SweepRow` (frozen): `task: str`, `mode: str`, plus the mode's payload as a `dict` (the existing
  report fields for that mode) **or** `error: str | None`.
- `SweepReport` (frozen): `mode`, `budget`, `seed`, `tasks_run`, `tasks_failed`, `rows: list[SweepRow]`,
  and a `summary` dict: `auc_sum` (sum over successful rows of the mode's headline AUC — `reproduce`:
  `auc_top10`; `head_to_head`: `llm_auc`; `analyzer_verdict`: `with_auc`), `published_sum` (= 13.751
  reference), and `beats` (count where the mode defines a beat: `head_to_head.beat` /
  `analyzer_verdict.helps`; `None` for `reproduce`).
- `run_sweep(tasks=PMO_TASKS, *, budget, seed, mode, pop_size, offspring, mutation_rate) -> SweepReport` —
  loops tasks, dispatches by mode to the existing primitive, wraps each in try/except for isolation, builds
  the report. No new AUC/comparator logic; pure orchestration + aggregation.

### CLI — `packages/core/capychem/eval/cli.py` (modify)
- Add `--all` (store_true). When set: derive `mode` from the existing flags (`--analyzer-verdict` →
  `analyzer_verdict`, `--head-to-head` → `head_to_head`, else `reproduce`), call `run_sweep`, and emit a
  combined JSON report (`{sweep: true, mode, budget, seed, tasks_run, tasks_failed, summary, rows}`). The
  single-task paths are untouched.

### UI — `apps/web/app/page.tsx` (modify) + `apps/web/lib/api.ts` (unchanged: `task` already `string`)
- A `PMO_TASKS` const (23, mirroring core) feeds a `<select>` (canonical order). `task` state defaults to
  `jnk3`; threaded into `createRun({ task, mutation_strategy: strategy, ...form })`. Title generalized.

## Data flow

```
launch (UI/API):  user picks task ∈ PMO_TASKS → field_validator OK → RunConfig.task → loop (unchanged)
sweep (CLI):      capychem-eval --all [--head-to-head|--analyzer-verdict] --budget B --seed S
                    → run_sweep(PMO_TASKS, mode=…) → per task: existing primitive (try/except) → SweepReport JSON
```

## Error handling

- **Unknown task at the API boundary** → `field_validator` raises → 422 with a clear message (FR-015).
- **A task fails mid-sweep** (oracle/proposer/verdict exception) → caught in `run_sweep`; the row records
  `error=str(exc)`, `tasks_failed += 1`; the sweep continues. Summary aggregates only successful rows.
- **Empty/degenerate aggregation** (all tasks failed) → `auc_sum=0.0`, `tasks_run=0`, `beats=0/None`; the
  report is still well-formed JSON (no crash).

## Observability

No loop/LangGraph change → no new spans. The sweep is a headless CLI; its report JSON is the artifact. Each
underlying primitive already carries its own observability (none for the headless eval path, by design).

## Testing (TDD, all harness-free / cost-free via the established monkeypatch pattern)

- **`test_eval_tasks.py` (new):** `PMO_TASKS` has 23 unique entries; canonical first entry `qed`; contains
  the milestone-02 tasks `qed`/`jnk3`.
- **`test_eval_baselines.py` (extend):** `set(GRAPH_GA_AUC_TOP10) == set(PMO_TASKS)`; `sum(...)` ≈ 13.751
  (abs tol 0.001); spot-check a few published values (jnk3 0.553, drd2 0.964, valsartan_smarts 0.000).
- **`test_task_surface.py` (fix + extend):** the unknown-task test switches to `not_a_real_task` (still 422);
  add that `drd2` (and a sampling of the 23) is now accepted; the default stays `qed`.
- **`test_eval_sweep.py` (new):** `run_sweep` over a small task list with **stubbed** per-task primitives —
  aggregation across all three modes (auc_sum, beats count, published_sum); per-task error isolation (one
  stubbed task raises → recorded as an error row, sweep completes, summary counts the rest).
- **`test_eval_cli.py` (extend):** `--all` wiring with a stubbed `run_sweep` — default mode `reproduce`;
  `--all --analyzer-verdict` selects `analyzer_verdict`; `--all --head-to-head` selects `head_to_head`; the
  combined report shape is emitted.
- **web (vitest / e2e):** the selector renders the 23 options, defaults to jnk3, and submitting threads the
  selected `task` into the create-run payload; `e2e/launch.spec.ts` updated for the new title/selector.

Quality gate before merge: `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .`
· `pnpm --filter web test` · `pnpm --filter web typecheck` · `pnpm --filter web lint`.

## Out of scope (deferred, explicit)

Executing the real 23-task sweep (slice 05, cost-bounded, confirm-before-invoke) · the Week-8 ≥3/23 verdict +
cost-gate-at-scale validation (slice 05) · per-task published-baseline hints in the UI · a `GET /tasks`
endpoint · any harness/oracle/analyzer/proposer behavior change · multi-objective · the live WS hypothesis
surface (slice 03).
