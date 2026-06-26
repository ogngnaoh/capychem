# Launch & watch jnk3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `jnk3` a launchable + watch-live target on the existing Graph-GA loop — the harness scores it, the API accepts it, and a jnk3-targeted web form starts a run and routes to its live view.

**Architecture:** Four vertical changes, bottom-up: (1) re-pin the isolated harness env so jnk3's legacy RandomForest pickle loads (scikit-learn `==1.2.2` + `numpy<2` + two `sys.modules` shims), (2) widen the API task `Literal` to `{qed, jnk3}`, (3) point the web launch form at jnk3 and expose `mutation_strategy` + `plateau_window`, (4) update the opt-in Playwright smoke. A final in-session task runs the full gate and a live launch→watch acceptance.

**Tech Stack:** Python 3.10 harness (PyTDC 0.3.6, isolated uv env) reached via subprocess+JSON; FastAPI + Pydantic; Next.js 16 / React 19 / TypeScript; Vitest + Testing Library; Playwright.

## Global Constraints

- **Never import from `harness/`** — subprocess + JSON only. (CLAUDE.md)
- **Harness env is isolated** — its own `pyproject.toml` + `uv.lock`, rebuilt via `uv sync --project harness`; never `uv add` legacy deps into the modern env.
- **Validate every SMILES via RDKit before persistence.** (not touched here; the loop's `validate` node already does)
- **FR-015** — refuse misconfigured launches at the API boundary (no/unknown task, non-positive budget) and explain.
- **Frontend WS uses an absolute URL** — no proxying through Next.js middleware. (not touched here)
- **Cost tracking stays first-class.** (not touched here)
- **TDD** — a failing test precedes production code. Frontend: Vitest for component logic, Playwright (opt-in) for the flow.
- **Secrets stay in `.env.local`** — never committed.
- **Verified facts (do not re-derive):** sklearn `==1.2.2` is the newest keeping the 7-field tree-node dtype the jnk3/gsk3b/drd2 pickles need (1.3.0 added `missing_go_to_left`); the pickle needs **two** shims (`sklearn.ensemble.forest`→`_forest`, `sklearn.tree.tree`→`sklearn.tree._classes`); rdkit `2026.03.2` co-resolves with `numpy<2`, so rdkit is **unchanged** and Graph-GA stays byte-identical; the proposer backend defaults to `stub`, so an `llm` launch runs without error in default config.
- **Merge gate (all must pass):** `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .` · `pnpm --filter web test` · `pnpm --filter web typecheck` · `pnpm --filter web lint`.

---

### Task 1: Harness jnk3 oracle fix

Re-pin the harness env and shim the legacy sklearn module paths so `jnk3` scores through the subprocess bridge. Re-verify milestone-01's qed/Graph-GA contract is intact (rdkit unchanged ⇒ it is).

**Files:**
- Create: `packages/core/tests/test_oracle_jnk3.py`
- Modify: `harness/pyproject.toml` (dependencies)
- Modify: `harness/capychem_harness/score.py` (~line 60, before `from tdc import Oracle`)
- Regenerate: `harness/uv.lock` (via `uv sync --project harness`)
- Modify: `.gitignore` (add `oracle/`)

**Interfaces:**
- Consumes: `capychem.oracle.score_smiles(smiles: list[str], task: str) -> list[OracleResult]` (existing); the `harness` fixture from `packages/core/tests/conftest.py` (skips when no harness venv).
- Produces: nothing new for later tasks — this is the bottom of the stack. `score_smiles([...], "jnk3")` now returns scored `OracleResult`s.

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_oracle_jnk3.py`:

```python
"""End-to-end test that the jnk3 PyTDC oracle scores through the re-pinned harness.

jnk3's RandomForest pickle predates the harness's scikit-learn; this proves the
sklearn<1.3 pin + the sys.modules shims make it load and score with a real spread.
Skips when no harness venv is reachable (mirrors the other harness-backed tests).
"""

from __future__ import annotations

from capychem.oracle import score_smiles


def test_jnk3_scores_with_spread(harness: None) -> None:
    # Drug-like seeds score across a range; tiny non-drug-like molecules score ~0.
    # A degenerate (all-equal) result would mean a silently-corrupt cross-version
    # unpickle — which would invalidate the slice-06 beat verdict.
    smis = [
        "c1ccccc1",
        "O=C(O)c1ccccc1",
        "CC(C)Nc1nc(Nc2ccc(N3CCOCC3)cc2)ncc1C(F)(F)F",
        "O=C(Nc1ccc(-c2ccncc2)cc1)c1ccc(F)cc1",
    ]
    results = score_smiles(smis, task="jnk3")
    assert len(results) == len(smis)
    for r in results:
        assert r.valid
        assert r.score is not None
        assert 0.0 <= r.score <= 1.0
    scores = [r.score for r in results if r.score is not None]
    assert max(scores) > min(scores)  # non-degenerate spread
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest packages/core/tests/test_oracle_jnk3.py -x`
Expected: FAIL — `HarnessError: Construct a valid PyTDC oracle for task 'jnk3': No module named 'sklearn.ensemble.forest'` (or a tree-node dtype `ValueError`), because the current harness runs scikit-learn 1.7.2.

- [ ] **Step 3: Re-pin the harness dependencies**

In `harness/pyproject.toml`, change the `dependencies` list so the `numpy` entry is constrained and scikit-learn is pinned:

```toml
dependencies = [
    "pytdc==0.3.6",
    # PyTDC 0.3.6 imports these at runtime but does not declare them.
    "rdkit",
    "requests",
    "networkx",
    "scipy",
    "numpy<2",              # scikit-learn 1.2.2 + the legacy jnk3 RF pickle need numpy 1.x
    "scikit-learn==1.2.2",  # newest sklearn keeping the 7-field tree-node dtype the jnk3/gsk3b/drd2 pickles need
]
```

- [ ] **Step 4: Add the sklearn module-path shims**

In `harness/capychem_harness/score.py`, inside the `try:` block that imports the oracle, immediately **before** `from tdc import Oracle`, add (right after the existing `rdkit.six` shim block):

```python
        # PyTDC 0.3.6's ML-model oracles (jnk3/gsk3b/drd2) unpickle a RandomForest
        # saved under scikit-learn ~0.21, whose module paths were renamed in 0.22.
        # Alias the old paths to the modern ones (sklearn is pinned <1.3 so the tree
        # node dtype still matches). qed is analytic and never triggers this unpickle.
        import sklearn.ensemble._forest  # noqa: F401
        import sklearn.tree._classes  # noqa: F401

        sys.modules.setdefault("sklearn.ensemble.forest", sys.modules["sklearn.ensemble._forest"])
        sys.modules.setdefault("sklearn.tree.tree", sys.modules["sklearn.tree._classes"])
```

- [ ] **Step 5: Rebuild the harness env + lockfile**

Run: `uv sync --project harness`
Expected: re-resolves `harness/uv.lock`; installs scikit-learn 1.2.2 + numpy 1.26.x.

Then assert rdkit is unchanged (so Graph-GA stays byte-identical):
Run: `harness/.venv/bin/python -c "import rdkit, numpy, sklearn; print(rdkit.__version__, numpy.__version__, sklearn.__version__)"`
Expected: `2026.03.2 1.26.x 1.2.2`. If rdkit changed, add `"rdkit==2026.3.2"` to the deps and re-sync before proceeding.

- [ ] **Step 6: Run the jnk3 test to verify it passes**

Run: `uv run pytest packages/core/tests/test_oracle_jnk3.py -x`
Expected: PASS (first run loads the ~10 MB model once; `oracle/jnk3.pkl` is already cached locally).

- [ ] **Step 7: Re-verify the milestone-01 contract (full suite)**

Run: `uv run pytest`
Expected: all pass, including `test_oracle_bridge.py` (qed benzene ≈ 0.4426) and `test_eval_runner.py::test_smoke_real_harness_unique_budget` (qed through the harness, determinism). rdkit is unchanged, so Graph-GA reproduction is unaffected.

- [ ] **Step 8: Gitignore the oracle model cache**

In `.gitignore`, add under a fitting section (e.g. after the Modal block):

```
# PyTDC oracle model cache (downloaded to CWD on first ML-oracle run)
oracle/
```

- [ ] **Step 9: Lint the new test**

Run: `uv run ruff check packages/core/tests/test_oracle_jnk3.py`
Expected: clean.

- [ ] **Step 10: Commit**

```bash
git add harness/pyproject.toml harness/uv.lock harness/capychem_harness/score.py \
        packages/core/tests/test_oracle_jnk3.py .gitignore
git commit -m "feat(harness): score jnk3 — pin sklearn<1.3 + numpy<2, shim legacy module paths

jnk3/gsk3b/drd2 unpickle a RandomForest saved under sklearn ~0.21; pin
scikit-learn==1.2.2 (7-field tree dtype) + numpy<2 and alias the renamed
sklearn.ensemble.forest / sklearn.tree.tree module paths. rdkit unchanged
(co-resolves with numpy<2), so Graph-GA reproduction is byte-identical.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: API task surface (accept jnk3, refuse unknown)

Widen the request schema to accept `jnk3` alongside `qed`; pin FR-015 refusal of unknown tasks and confirm `mutation_strategy` / `plateau_window` reach `RunConfig`.

**Files:**
- Modify: `apps/api/capychem/api/schemas.py:11`
- Create: `apps/api/tests/test_task_surface.py`

**Interfaces:**
- Consumes: `CreateRunRequest` (Pydantic); `capychem.api.runner.RunRegistry.start_run(self, cfg: RunConfig) -> int`; the FastAPI app from `capychem.api.main`.
- Produces: `CreateRunRequest.task: Literal["qed", "jnk3"]` (default `"qed"`). No new symbols for later tasks.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_task_surface.py`:

```python
"""Task-surface validation: jnk3 accepted alongside qed; unknown tasks refused
(FR-015); launch config (task / mutation_strategy / plateau_window) reaches RunConfig.
The mapping test stubs RunRegistry.start_run so no real loop runs."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from capychem.api.main import app
from capychem.api.schemas import CreateRunRequest
from httpx_ws.transport import ASGIWebSocketTransport
from pydantic import ValidationError


def test_schema_accepts_jnk3_and_qed() -> None:
    assert CreateRunRequest(task="jnk3", budget=10).task == "jnk3"
    assert CreateRunRequest(task="qed", budget=10).task == "qed"
    assert CreateRunRequest(budget=10).task == "qed"  # default unchanged


def test_schema_rejects_unknown_task() -> None:
    with pytest.raises(ValidationError):
        CreateRunRequest(task="drd2", budget=10)


async def test_post_runs_maps_task_strategy_plateau_to_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from capychem.api import runner as runner_mod

    captured: dict[str, Any] = {}

    async def fake_start(self: Any, cfg: Any) -> int:
        captured["cfg"] = cfg
        return 4242

    monkeypatch.setattr(runner_mod.RunRegistry, "start_run", fake_start)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            body = {"task": "jnk3", "budget": 50, "mutation_strategy": "llm", "plateau_window": 7}
            r = await c.post("/runs", json=body)
            assert r.status_code == 201
            assert r.json()["run_id"] == 4242
    cfg = captured["cfg"]
    assert cfg.task == "jnk3"
    assert cfg.mutation_strategy == "llm"
    assert cfg.plateau_window == 7


async def test_post_runs_rejects_unknown_task() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r = await c.post("/runs", json={"task": "drd2", "budget": 10})
            assert r.status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest apps/api/tests/test_task_surface.py -x`
Expected: FAIL on `test_schema_accepts_jnk3_and_qed` — `ValidationError` for `task="jnk3"` (current `Literal["qed"]`).

- [ ] **Step 3: Widen the task Literal**

In `apps/api/capychem/api/schemas.py`, change line 11:

```python
    task: Literal["qed", "jnk3"] = "qed"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest apps/api/tests/test_task_surface.py -x`
Expected: PASS (the mapping + unknown-task tests need Postgres on :5432, already up in dev).

- [ ] **Step 5: Typecheck + lint**

Run: `uv run mypy -p capychem -p capychem.api && uv run ruff check apps/api`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/capychem/api/schemas.py apps/api/tests/test_task_surface.py
git commit -m "feat(api): accept jnk3 task alongside qed; refuse unknown tasks (FR-015)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Web launch form targets jnk3 (strategy + plateau fields)

Point the form at jnk3, add a `plateau_window` field and a native `mutation_strategy` select, and extend the `createRun` body type. Add the `@/` alias vitest needs to import the page.

**Files:**
- Modify: `apps/web/vitest.config.ts` (add `resolve.alias` for `@`)
- Modify: `apps/web/lib/api.ts` (`CreateRunBody`)
- Modify: `apps/web/app/page.tsx`
- Create: `apps/web/app/page.test.tsx`

**Interfaces:**
- Consumes: `createRun(body: CreateRunBody) => Promise<{ run_id: number }>` from `@/lib/api`; `useRouter()` from `next/navigation`.
- Produces: a form that calls `createRun` with `{ task: "jnk3", mutation_strategy, plateau_window, budget, seed, pop_size, offspring, mutation_rate, max_generations }`.

- [ ] **Step 1: Add the `@/` alias to vitest (test infra)**

Replace `apps/web/vitest.config.ts` with:

```typescript
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const root = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": resolve(root, ".") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["**/*.test.ts", "**/*.test.tsx"],
    exclude: ["e2e/**", "node_modules/**", ".next/**", "dist/**"],
  },
});
```

- [ ] **Step 2: Write the failing component test**

Create `apps/web/app/page.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createRun = vi.fn().mockResolvedValue({ run_id: 7 });
vi.mock("@/lib/api", () => ({ createRun: (...a: unknown[]) => createRun(...a) }));

import Home from "./page";

describe("launch form (jnk3)", () => {
  beforeEach(() => {
    createRun.mockClear();
    push.mockClear();
  });

  it("renders a jnk3-targeted form with strategy + plateau fields", () => {
    render(<Home />);
    screen.getByText(/Launch a jnk3 optimization/i);
    screen.getByLabelText(/Mutation strategy/i);
    screen.getByLabelText(/Plateau window/i);
  });

  it("submits task=jnk3 with the chosen strategy + plateau_window", async () => {
    render(<Home />);
    fireEvent.change(screen.getByLabelText(/Oracle-call budget/i), {
      target: { value: "120" },
    });
    fireEvent.change(screen.getByLabelText(/Mutation strategy/i), {
      target: { value: "llm" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start run/i }));

    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        task: "jnk3",
        mutation_strategy: "llm",
        plateau_window: 5,
        budget: 120,
      }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/runs/7"));
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pnpm --filter web test`
Expected: FAIL — no "Launch a jnk3 optimization" text / no "Mutation strategy" + "Plateau window" labels (the form still says QED and lacks both fields).

- [ ] **Step 4: Extend the `createRun` body type**

In `apps/web/lib/api.ts`, replace the `CreateRunBody` type:

```typescript
export type CreateRunBody = {
  task: string;
  budget: number;
  seed: number;
  pop_size: number;
  offspring: number;
  mutation_rate: number;
  plateau_window: number;
  max_generations: number;
  mutation_strategy: string;
};
```

- [ ] **Step 5: Update the launch form**

In `apps/web/app/page.tsx`:

(a) Add `plateau_window` to `DEFAULTS`:

```tsx
const DEFAULTS = {
  budget: 200,
  seed: 42,
  pop_size: 100,
  offspring: 32,
  mutation_rate: 0.01,
  plateau_window: 5,
  max_generations: 100,
};
```

(b) Add strategy state next to the existing `useState`s:

```tsx
  const [strategy, setStrategy] = useState<"graph_ga" | "llm">("graph_ga");
```

(c) Submit jnk3 + strategy (replace the `createRun({ task: "qed", ...form })` call):

```tsx
      const { run_id } = await createRun({
        task: "jnk3",
        mutation_strategy: strategy,
        ...form,
      });
```

(d) Retitle the card:

```tsx
          <CardTitle>Launch a jnk3 optimization</CardTitle>
```

(e) Add `plateau_window` to the numeric field list (the `as const` array):

```tsx
                ["mutation_rate", "Mutation rate"],
                ["plateau_window", "Plateau window"],
                ["max_generations", "Max generations"],
```

(f) Add the strategy `<select>` immediately before the submit row (`<div className="col-span-2 ...">`):

```tsx
            <div className="flex flex-col gap-1">
              <Label htmlFor="mutation_strategy">Mutation strategy</Label>
              <select
                id="mutation_strategy"
                value={strategy}
                onChange={(e) =>
                  setStrategy(e.target.value as "graph_ga" | "llm")
                }
                className="h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="graph_ga">Graph-GA</option>
                <option value="llm">LLM proposer</option>
              </select>
            </div>
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pnpm --filter web test`
Expected: PASS (both cases).

- [ ] **Step 7: Typecheck + lint**

Run: `pnpm --filter web typecheck && pnpm --filter web lint`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add apps/web/vitest.config.ts apps/web/lib/api.ts apps/web/app/page.tsx apps/web/app/page.test.tsx
git commit -m "feat(web): launch jnk3 with mutation_strategy + plateau_window fields

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Playwright smoke targets jnk3 (opt-in)

Update the opt-in e2e launch smoke to exercise the jnk3 form and its slower per-generation oracle. Not part of the merge gate (`pnpm --filter web test` is Vitest only); it runs against a live stack.

**Files:**
- Modify: `apps/web/e2e/launch.spec.ts`

**Interfaces:** none (browser-level smoke).

- [ ] **Step 1: Update the smoke for jnk3**

Replace `apps/web/e2e/launch.spec.ts` with:

```typescript
import { expect, test } from "@playwright/test";

// Opt-in smoke (pnpm --filter web test:e2e) — needs the live stack: Next dev,
// FastAPI, Postgres, harness venv. jnk3 reloads its ~10 MB model per generation,
// so the loop is slower than qed; keep the budget small and the timeout generous.
test("launch a jnk3 run and reach a terminal state", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/Launch a jnk3 optimization/i)).toBeVisible();
  await page.getByLabel("Oracle-call budget").fill("40");
  await page.getByLabel("Population size").fill("20");
  await page.getByLabel("Offspring / gen").fill("10");
  await page.getByLabel("Plateau window").fill("5");
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page).toHaveURL(/\/runs\/\d+/);
  await expect(
    page.getByText(/exhausted|max_generations|no_progress|stopped|errored/),
  ).toBeVisible({ timeout: 240000 });
  await expect(page.getByText("errored", { exact: true })).not.toBeVisible();
});
```

- [ ] **Step 2: Typecheck**

Run: `pnpm --filter web typecheck`
Expected: clean (the spec is type-checked but excluded from the Vitest gate).

- [ ] **Step 3: Commit**

```bash
git add apps/web/e2e/launch.spec.ts
git commit -m "test(web): point launch e2e smoke at jnk3

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Full gate + live launch→watch acceptance (in-session)

Not a subagent task — run by the lead in this session before shipping. Proves exit criterion 7 (jnk3 launchable + watchable live) end to end.

**Files:** none (verification only).

- [ ] **Step 1: Run the full merge gate**

```bash
uv run pytest
uv run mypy -p capychem -p capychem.api
uv run ruff check .
pnpm --filter web test
pnpm --filter web typecheck
pnpm --filter web lint
```
Expected: all green.

- [ ] **Step 2: Live acceptance (manual)**

With Postgres (:5432) + harness venv present, start the API and web:

```bash
uv run uvicorn capychem.api.main:app --reload          # :8000
pnpm --filter web dev                                   # :3000
```

In the browser at `http://localhost:3000`: confirm the form reads "Launch a jnk3 optimization", launch a jnk3 run (budget ~40, strategy Graph-GA), confirm the route lands on `/runs/{id}`, and watch the live view update (generation / best score / oracle-calls) within ~2 s of each `generation.complete`, reaching a terminal status without `errored`. Optionally run the opt-in `pnpm --filter web test:e2e` instead.

- [ ] **Step 3: (No commit)** — proceed to the slice-ship ritual once green.

---

## Self-Review

**Spec coverage:**
- Harness jnk3 fix (spec §1) → Task 1. ✓
- API `Literal["qed","jnk3"]` + FR-015 (spec §2) → Task 2. ✓
- Web form: jnk3 target, `plateau_window`, `mutation_strategy` select, `api.ts` (spec §3) → Task 3. ✓
- Watch-live confirmation + clean slice-02 seam (spec §4) → Task 4 (e2e) + Task 5 (live acceptance); `LiveRun.tsx` untouched. ✓
- Testing pyramid (spec §Testing): harness-gated jnk3 (T1), API fast (T2), Vitest (T3), Playwright opt-in (T4). ✓
- Re-verification gate (spec §1) → T1 Steps 5–7. ✓
- gitignore `oracle/` (spec decisions) → T1 Step 8. ✓

**Placeholder scan:** none — every code/test/command step carries concrete content.

**Type consistency:** `CreateRunBody` (T3) gains `plateau_window: number` + `mutation_strategy: string`, matching the form's `createRun({ task, mutation_strategy, plateau_window, ...form })` call and the API's existing `mutation_strategy`/`plateau_window` request fields. `RunRegistry.start_run(self, cfg)` stub in T2 matches the real signature used in `routes_runs.py`. `task: Literal["qed","jnk3"]` is consistent across T2's tests and schema.
