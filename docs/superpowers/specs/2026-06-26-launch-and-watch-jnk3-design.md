# Design — Launch & watch jnk3 (milestone 02, slice 01)

**Date:** 2026-06-26
**Slice:** `01-launch-and-watch-jnk3`
**Milestone:** `02-end-to-end-loop` (SPEC Phase 2)
**Deps:** none (dep-free; unblocks the slice-06 finale, which needs 01 + 04 + 05)
**Status:** approved (design); pre-implementation

## Problem

`jnk3` is not a launchable target end-to-end. Two gaps:

1. **The jnk3 oracle does not score through the harness.** The launch→oracle path
   already carries the task name cleanly (`RunConfig.task` → `score_smiles(smiles,
   task)` → harness `Oracle(name=task)`; the harness has no hardcoded task list,
   and the seed population `starting_pop.smi` is task-agnostic). But jnk3's PyTDC
   oracle unpickles a RandomForest saved under scikit-learn ~0.21, and the harness
   env runs scikit-learn **1.7.2**. Constructing `Oracle(name="jnk3")` fails:
   - A `sys.modules` module-path shim alone (mirroring the existing `rdkit.six`
     shim in `harness/capychem_harness/score.py`) gets past the *import* but then
     hits a hard **tree-node dtype mismatch** — the pickle's tree nodes have 7
     fields; scikit-learn ≥1.3 expects 8 (`missing_go_to_left`, added in 1.3.0).
   - qed is unaffected because it is analytic (RDKit), no pickle.

2. **The web cannot launch jnk3.** `apps/web/app/page.tsx` hardcodes `task: "qed"`,
   titles itself "Launch a QED optimization", and omits the `plateau_window` and
   `mutation_strategy` fields that FR-001 lists. The API schema also gates the task
   name: `CreateRunRequest.task: Literal["qed"]`.

Watch-live is **already built**: `apps/web/app/runs/[id]/LiveRun.tsx` renders
generation / oracle-calls / best-score / cost / AUC chart / top-molecules over the
WS and applies `generation.complete` / `run.complete`. It displays `snap.task`, so
it reads "jnk3" for free. Slice-01 work on watch-live is *confirmation*, not new
rendering.

This slice makes jnk3 score through the (re-pinned) harness, accepts it at the API
boundary alongside qed, and launches it from a jnk3-targeted web form that also
exposes `mutation_strategy` + `plateau_window` (FR-001) — satisfying Story 1
(launch) and Story 2 (watch-live) for the single chosen task.

## Verified spike evidence

The harness fix was proven in an isolated ephemeral venv (no touch to
`harness/.venv`), loading the real cached `oracle/jnk3.pkl`:

- **scikit-learn 1.3.2 + numpy<2:** still fails (1.3.2 expects the 8-field dtype).
- **scikit-learn 1.2.2 + numpy 1.26.4 + both shims:** jnk3 constructs in ~10 s
  (first pickle load), scores ~15 ms/molecule, and gives a **non-degenerate
  spread** — 40 starting-pop molecules → 22 nonzero, mean 0.019, max 0.12; a
  kinase-inhibitor-like probe scored **0.51** vs ~0 for benzene/ethanol. This
  rules out a silently-corrupt cross-version unpickle (which would have invalidated
  slice-06's beat verdict).
- The pickle needs **two** shims, not one: `sklearn.ensemble.forest` →
  `sklearn.ensemble._forest` **and** `sklearn.tree.tree` → `sklearn.tree._classes`.

## Goals

1. `score_smiles([...], "jnk3")` returns valid in-silico scores in [0,1] with a
   real spread, through the isolated harness subprocess (no import).
2. Milestone-01's frozen reproducibility contract still holds after the harness
   re-pin (qed scoring + Graph-GA reproduction green).
3. The API accepts `task ∈ {"qed", "jnk3"}` and refuses an unknown task (FR-015).
4. The web app configures + starts a jnk3 run (task, budget, `mutation_strategy`,
   `plateau_window`, seed) and routes to its live view (Story 1 / FR-001).
5. The live view shows generation / best-so-far / oracle-calls updating within ~2 s
   of each generation event over the WS, for a jnk3 run (Story 2 / FR-009).

Maps to milestone-02 exit criterion **7** (jnk3 launchable + watchable live).

## Non-goals (explicitly deferred)

- **Plateau stop + live plateau signal** — slice 02. This slice leaves the seam
  clean: it does **not** add `plateaued` to `LiveRun`'s terminal-status set or any
  plateau UI; `plateau_window` is captured as config only.
- **LLM-proposer beat-Graph-GA verdict run** — slice 06. Exposing the
  `mutation_strategy` selector does not re-validate the llm path end-to-end (slices
  04/06 own that).
- **valid_smiles gate-purity fix** — slice-06 BLOCKER; untouched here.
- Analyzer step + full 23-task selector — milestone 03. Compare view — milestone 04.
- Expensive oracles, multi-objective — stretch / out of milestone.

## Key decisions (resolved)

- **Pin scikit-learn `==1.2.2` + `numpy<2` in the harness env** (not a runtime
  shim alone — proven insufficient). 1.2.2 is the newest scikit-learn that keeps
  the 7-field tree dtype the pickle needs; it requires numpy 1.x. The two
  `sys.modules` shims stay (the 1.2.x module layout is `_forest`/`_classes`, the
  pickle references the pre-0.22 `forest`/`tree.tree` paths).
- **API accepts `Literal["qed", "jnk3"]`, default stays `"qed"`.** qed is kept as
  the instant analytic smoke task ~20 existing tests + the eval baseline depend on;
  jnk3 is added alongside. Keeping the default `"qed"` means existing API tests that
  omit `task` are untouched. This is **not** a UI multi-task selector (m03) — the
  web targets jnk3 only.
- **`mutation_strategy` selector is a native `<select>`** (`graph_ga` | `llm`),
  default `graph_ga` — no new shadcn dependency for a two-option choice. Exposing
  `llm` is safe: the proposer backend defaults to `stub` (deterministic,
  network-free), so an `llm` launch runs without error in default config; `llm` +
  the `direct` backend without `DEEPSEEK_API_KEY` errors the run (existing slice-04
  behavior, the operator's choice). No special handling added this slice.
- **`oracle/` is gitignored.** TDC downloads `jnk3.pkl` (~10 MB) to the process CWD
  on first jnk3 run (the subprocess inherits the parent CWD; for the dev server and
  pytest that is repo root). The model is a cache artifact, not source.

## Design

### 1. Harness jnk3 oracle fix (load-bearing)

`harness/pyproject.toml` — add to `dependencies`:

```
"scikit-learn==1.2.2",  # jnk3/gsk3b/drd2 RF pickles predate sklearn 1.3's 8-field tree node dtype
```

and constrain the existing `"numpy"` entry to `"numpy<2"` (scikit-learn 1.2.2 +
the legacy pickles need numpy 1.x). Re-resolve `harness/uv.lock` via
`uv sync --project harness`. scikit-learn is currently pulled *transitively* by
PyTDC (1.7.2); the explicit pin overrides it.

`harness/capychem_harness/score.py` — before `Oracle(name=task)`, add two guarded,
idempotent `sys.modules` aliases next to the existing `rdkit.six` shim:

```
import sklearn.ensemble._forest
import sklearn.tree._classes
sys.modules.setdefault("sklearn.ensemble.forest", sys.modules["sklearn.ensemble._forest"])
sys.modules.setdefault("sklearn.tree.tree", sys.modules["sklearn.tree._classes"])
```

(Done unconditionally on every score call as the rdkit.six shim is — cheap, and
only the ML-model oracles reference these paths; qed never triggers the unpickle.)

`.gitignore` — add `oracle/`.

**Re-verification gate (before any app code):** `uv run pytest` exercises qed
scoring + Graph-GA through the re-pinned harness; the reproduction test confirms
the milestone-01 contract. If a reproduction drifts past `DEFAULT_TOLERANCE`
(0.02) — plausibly via an rdkit downgrade forced by `numpy<2` — investigate before
proceeding.

### 2. API task surface

`apps/api/capychem/api/schemas.py` — `CreateRunRequest.task`:

```
task: Literal["qed", "jnk3"] = "qed"
```

No other API change: `mutation_strategy: Literal["graph_ga", "llm"] = "graph_ga"`
and `plateau_window: int = Field(default=5, gt=0)` already exist on the request and
already flow `RunConfig` → `Run` columns via `create_run_endpoint` / `run.py`.
FR-015 (refuse no/invalid task, non-positive budget) is already enforced —
budget `gt=0` and the task `Literal` both 422 in Pydantic; this slice pins it with
a test.

### 3. Web launch form

`apps/web/app/page.tsx`:

- Submit `task: "jnk3"` (replacing the hardcoded `"qed"`); retitle "Launch a jnk3
  optimization".
- Add a `plateau_window` number field (default 5) to `DEFAULTS` + the field grid.
- Add a `mutation_strategy` native `<select>` (`graph_ga` | `llm`, default
  `graph_ga`), styled with the existing Tailwind tokens to match the inputs.
- Existing client-side guards (budget > 0, pop_size > 1) stay; the API is
  authoritative.

`apps/web/lib/api.ts` — extend `CreateRunBody` with
`mutation_strategy: string` and `plateau_window: number`.

### 4. Watch-live (confirmation + clean seam)

`LiveRun.tsx` is unchanged. It already satisfies Story 2 for jnk3 (renders
`snap.task` = "jnk3"; updates per `generation.complete`). The `plateaued` status
and plateau signal are **slice 02's** — not added here, so the seam stays clean.
Confirmation is via the Playwright smoke (§Testing).

## Data flow

`page.tsx` (task=jnk3, mutation_strategy, plateau_window, budget, seed, …) →
`POST /runs` → `CreateRunRequest` (422 on bad task/budget) → `RunConfig` →
in-process runner → loop `propose` (graph_ga) → `validate` (RDKit) →
`score_smiles(…, "jnk3")` → harness subprocess (re-pinned, shimmed) → persist
Candidate/OracleCall + `generation.complete` over WS → `LiveRun` re-renders within
~2 s.

## Testing (TDD — a failing test precedes each change)

**Harness (`packages/core/tests/`, harness-gated/slow):**
- New: `score_smiles(["c1ccccc1", <drug-like seeds…>], "jnk3")` returns `valid` rows
  with `score` floats in [0,1] and a non-degenerate spread (≥1 nonzero, not all
  equal). Skips when the harness venv is absent (guard on
  `_harness_python().exists()`, mirroring existing harness-gated tests) — so CI
  without the harness venv skips cleanly. Caveat for the plan: the first jnk3 score
  downloads `oracle/jnk3.pkl` (~10 MB) via TDC; with the venv present but no cached
  model + no network the test would error, so the plan decides whether to also guard
  on model presence (the model is already cached locally from the design spike).
  This is the jnk3-end-to-end proof.
- The existing qed harness/reproduction tests stay green post-pin = milestone-01
  re-verification (no new test; the full suite is the gate).

**API (`apps/api/tests/`, fast — no full jnk3 loop):**
- `POST /runs` with an unknown task (e.g. `"drd2"`) → 422 (FR-015).
- jnk3 is accepted by `CreateRunRequest`; `mutation_strategy` + `plateau_window`
  from the body land in the constructed `RunConfig`.

**Web (`apps/web/`, Vitest + Testing Library):**
- `app/page.test.tsx`: renders the jnk3 title, a `mutation_strategy` select, and a
  `plateau_window` field; submitting calls `createRun` with `{task:"jnk3",
  mutation_strategy, plateau_window, budget, seed, …}` (mock `@/lib/api` +
  `next/navigation`).

**Web (Playwright, opt-in — `test:e2e`, NOT in the `vitest run` gate):**
- Update `e2e/launch.spec.ts` to drive the jnk3 form (incl. plateau window) →
  `/runs/{id}` → a terminal state without `errored` (watch-live confirmation).

Gate green before merge: `uv run pytest` · `uv run mypy -p capychem -p capychem.api`
· `uv run ruff check .` · `pnpm --filter web test` · `pnpm --filter web typecheck`
· `pnpm --filter web lint`.

## Files touched

- `harness/pyproject.toml` — pin `scikit-learn==1.2.2`, constrain `numpy<2`.
- `harness/uv.lock` — re-resolved by `uv sync --project harness`.
- `harness/capychem_harness/score.py` — two sklearn `sys.modules` shims.
- `.gitignore` — add `oracle/`.
- `apps/api/capychem/api/schemas.py` — `task: Literal["qed", "jnk3"]`.
- `apps/web/app/page.tsx` — jnk3 target, title, `plateau_window`, `mutation_strategy`.
- `apps/web/lib/api.ts` — `CreateRunBody` gains `mutation_strategy` + `plateau_window`.
- `apps/web/e2e/launch.spec.ts` — jnk3 launch smoke.
- New tests: `packages/core/tests/` (jnk3 harness score), `apps/api/tests/`
  (task validation + config flow), `apps/web/app/page.test.tsx`.

Untouched: `LiveRun.tsx`, `runner.py`, `ws_runs.py`, `loop/` (graph/state/logic),
`eval/`, `validate.py`, `proposer.py`, `strategy.py`, `db/models.py` (no migration).

## Top risk

`numpy<2` may downgrade the harness's `rdkit` during re-resolution, which *could*
shift Graph-GA canonical SMILES and nudge the qed reproduction AUC. Mitigation: the
§1 full-suite re-verification gate; if a reproduction test drifts past tolerance,
investigate (e.g. pin rdkit too) before proceeding to app code.
