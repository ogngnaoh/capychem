# CapyChem Fork-and-Run Polish + Demo Enablement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the shipped CapyChem repo for a recorded demo via two low-risk bundles — (A) make a fresh clone frictionless, and (B) produce a committed, honest, deterministic demo GIF — without reopening the milestone-07 engine or shipped UI.

**Architecture:** Bundle A is DX/packaging/docs only (a Makefile, one dependency move, one CLI env-load fix, doc corrections). Bundle B adds a deterministic Playwright video click-through over the existing `_fixtures.ts` mock path — extending the mock WebSocket to *replay* a scripted event sequence so the live cockpit visibly ticks — then converts the video to `docs/assets/demo.gif`. Nothing in either bundle touches the loop engine or the request path.

**Tech Stack:** Python 3.12 (uv workspaces), FastAPI, Next.js 16 / React 19 / TypeScript, Playwright (video capture), ffmpeg (webm→gif), Makefile.

## Global Constraints

Copied verbatim from the handoff / project docs — every task implicitly includes these:

- **N6 (in-silico only):** every score is a standardized in-silico oracle score; never a real-world drug-discovery efficacy claim in code, copy, README, or narration.
- **Figure canon (verbatim, never a bare fraction):** "beats or matches Graph-GA on all 21 comparable PMO tasks · decisive on 9 · 2 of 23 excluded for cause (defective oracles, not losses) · bar ≥6/23." Never write "21/23" or "23/23".
- **Demo honesty guardrails in-frame:** `ModeBadge` "Exploratory · not benchmark-comparable" on custom shots; in-silico tags on every surface; Compare declares a winner only for same-objective + both-benchmark; the FR-015 "no benchmark matches" refusal is a FEATURE to show, not a blooper; the live cockpit beat never claims "beating" (its data is honestly behind baseline at gen 10); any live clip is budget-capped and labelled "live run".
- **No milestone-07 regression:** keep every gate green — backend `mypy` / `ruff` / `pytest`; web `typecheck` / ESLint / `vitest` / axe WCAG-AA; no horizontal scroll @1280px. Bundle B touches only `apps/web` + `docs`; Bundle A touches DX/docs/packaging. Neither reopens the loop engine or shipped UI surfaces beyond the files listed.
- **Branch-first:** all work lands on a branch off `main` (never commit engine/UI changes directly to `main`). `main` is currently 22 commits ahead of `origin/main` and unpushed — do not push as part of this work unless asked.

## File Structure

**Bundle A**
- `Makefile` — *create*. `setup` / `dev` / `test` / `check` targets.
- `pyproject.toml` — *modify*. Root: `httpx` stays only if still needed by dev; it moves to core.
- `packages/core/pyproject.toml` — *modify*. Add `httpx` to runtime `dependencies`.
- `packages/core/capychem/eval/cli.py` — *modify*. Call `load_local_env()` first in `main()`.
- `packages/core/tests/test_eval_cli_env.py` — *create*. Assert the eval CLI loads `.env.local`.
- `CLAUDE.md` — *modify*. Fix the stale "Test single" path; add the Makefile + demo-capture commands (the latter in Task B4).
- `.nvmrc` — *create*. `22`.
- `package.json` (root) — *modify*. Add `engines`.
- `README.md` — *modify*. Document `make setup`/`make dev`; mark `alembic upgrade head` redundant-if-API-started; label Langfuse OPTIONAL; add harness-Python-3.10 + `pytest`-needs-Postgres notes. (Demo GIF embed is Task B4.)

**Bundle B**
- `apps/web/e2e/_fixtures.ts` — *modify*. Repoint `COMPARE_PAYLOAD.b` → run 268 (both-benchmark); add `snapshotById` to `MockOpts`/`mockApi`; add `stubWebSocketReplay`, `SNAPSHOT_REPLAY_START`, `DEMO_REPLAY_EVENTS`.
- `apps/web/e2e/compare-shot.spec.ts` — *modify*. Update the URL to `b=268` and assert the green verdict.
- `apps/web/app/compare/CompareView.test.tsx` — *modify (if it pins the exploratory default)*. Keep it green.
- `apps/web/e2e/demo.spec.ts` — *create*. Single video-recorded 13-shot click-through.
- `docs/assets/demo.gif` — *create* (generated). Embedded at the top of `README.md`.

---

## Task 1: Move `httpx` to `packages/core` runtime dependency

Only `httpx` is a real runtime import — `packages/core/capychem/proposer.py:207` (`import httpx`) on the `direct` proposer path. `httpx-ws` is test-only (no runtime import anywhere in `packages/core`/`apps/api`/`apps/worker`) and **stays** in root dev. A wheel or `uv sync --no-dev` currently ImportErrors on the real-LLM path because `httpx` sits in `[dependency-groups].dev`.

**Files:**
- Modify: `packages/core/pyproject.toml` (runtime `dependencies`)
- Modify: `pyproject.toml` (root `[dependency-groups].dev`)

**Interfaces:**
- Produces: `httpx` importable from a `--no-dev` install of `capychem-core`.

- [ ] **Step 1: Read the current core deps block**

Run: `sed -n '1,20p' packages/core/pyproject.toml`
Confirm the `dependencies = [ ... ]` list and its style (quoting, version floors).

- [ ] **Step 2: Add `httpx` to core runtime deps**

In `packages/core/pyproject.toml`, add to the `dependencies` array (match existing floor style; root uses `>=0.27`):

```toml
    "httpx>=0.27",
```

- [ ] **Step 3: Remove `httpx` from root dev group; keep `httpx-ws`**

In `pyproject.toml`, delete the `"httpx>=0.27",` line from `[dependency-groups].dev` (lines ~29). **Leave `"httpx-ws>=0.6",`** — it is test-only. `httpx` will now resolve for dev too, transitively via `capychem-core`.

- [ ] **Step 4: Re-lock and verify a no-dev install exposes httpx**

Run:
```bash
uv sync && uv sync --no-dev && uv run --no-dev python -c "import capychem.proposer, httpx; print('ok', httpx.__version__)"
```
Expected: prints `ok <version>` with no ImportError. Then restore the dev env: `uv sync`.

- [ ] **Step 5: Confirm the proposer's direct path still imports**

Run: `uv run python -c "import capychem.proposer as p; print('proposer import ok')"`
Expected: `proposer import ok`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml packages/core/pyproject.toml uv.lock
git commit -m "fix(deps): move httpx to core runtime so the direct LLM path survives --no-dev"
```

---

## Task 2: Load `.env.local` in the eval CLI

`capychem-eval` (`packages/core/capychem/eval/cli.py`) never calls `load_local_env()`, so `--mutation-strategy=llm` silently runs the deterministic stub when `DEEPSEEK_API_KEY` lives only in `.env.local` — no error, fake "LLM" results. Mirror the exact pattern already used in `packages/core/capychem/cli.py:113-115` and `apps/api/capychem/api/main.py:29-31`.

**Files:**
- Modify: `packages/core/capychem/eval/cli.py`
- Test: `packages/core/tests/test_eval_cli_env.py`

**Interfaces:**
- Consumes: `capychem.env.load_local_env` (signature `load_local_env(path: Path | None = None) -> None`).
- Produces: `capychem.eval.cli.main` calls `load_local_env()` before parsing args.

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_eval_cli_env.py`:

```python
"""The eval CLI must load .env.local so an --mutation-strategy=llm eval doesn't
silently fall back to the stub when the key lives only in .env.local (a fresh-fork
footgun; the API lifespan and capychem-run already do this)."""

import pytest

from capychem.eval import cli


def test_eval_cli_main_loads_local_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = {"n": 0}
    monkeypatch.setattr(cli, "load_local_env", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    # --help exits early via argparse; load_local_env must already have run by then.
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert called["n"] == 1
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest packages/core/tests/test_eval_cli_env.py -x`
Expected: FAIL — either `AttributeError: ... has no attribute 'load_local_env'` (not imported yet) or `assert 0 == 1` (never called).

- [ ] **Step 3: Import and call `load_local_env` first in `main()`**

In `packages/core/capychem/eval/cli.py`, add the import near the top (module level, with the other imports):

```python
from capychem.env import load_local_env
```

Then make it the **first statement** of `main()` (before `argparse` builds the parser, so `--help` still triggers it and so the key is present regardless of arg order):

```python
def main(argv: list[str] | None = None) -> int:
    load_local_env()  # .env.local → DEEPSEEK_API_KEY reaches an --mutation-strategy=llm eval
    p = argparse.ArgumentParser(...)
    ...
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `uv run pytest packages/core/tests/test_eval_cli_env.py -x`
Expected: PASS.

- [ ] **Step 5: Confirm the CLI still runs (no import cycle)**

Run: `uv run capychem-eval --help`
Expected: usage text prints, exit 0.

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/eval/cli.py packages/core/tests/test_eval_cli_env.py
git commit -m "fix(eval): load .env.local in capychem-eval so LLM eval doesn't silently stub"
```

---

## Task 3: Fix the stale "Test single" path in `CLAUDE.md`

`CLAUDE.md:36` cites `packages/core/tests/test_loop.py::test_invalid_smiles_falls_back` — that file does not exist. The real invalid→fallback test is `packages/core/tests/test_loop_fallback.py::test_fallback_backfills_gap_for_llm` (verified present, line 30).

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Verify the real test name and that it passes**

Run: `uv run pytest "packages/core/tests/test_loop_fallback.py::test_fallback_backfills_gap_for_llm" -x`
Expected: PASS (this is the command the doc will cite).

- [ ] **Step 2: Update the doc line**

In `CLAUDE.md`, replace:
```
- `uv run pytest packages/core/tests/test_loop.py::test_invalid_smiles_falls_back -x`
```
with:
```
- `uv run pytest packages/core/tests/test_loop_fallback.py::test_fallback_backfills_gap_for_llm -x`
```

- [ ] **Step 3: Commit** (fold into Task 5's doc commit if executing inline — otherwise:)

```bash
git add CLAUDE.md
git commit -m "docs: fix stale Test-single path (test_loop.py never existed)"
```

---

## Task 4: Add a `Makefile` and Node pinning

Collapse the 7-step ordering hazard into `make setup` / `make dev`. Use a Makefile (not a justfile) so a fresh forker needs zero extra install (`make` ships with macOS Xcode CLT, which any dev cloning this already has). Pin Node.

**Files:**
- Create: `Makefile`
- Create: `.nvmrc`
- Modify: `package.json` (root — add `engines`)

- [ ] **Step 1: Create `.nvmrc`**

```
22
```

- [ ] **Step 2: Add `engines` to root `package.json`**

Read it first (`sed -n '1,10p' package.json`), then add an `engines` block alongside `packageManager`:

```json
  "engines": {
    "node": ">=22",
    "pnpm": ">=11.5.0"
  },
```

- [ ] **Step 3: Create the `Makefile`**

Use **tab** indentation (Makefiles require real tabs). `cp -n` never clobbers an existing `.env.local`.

```makefile
# CapyChem developer shortcuts. `make setup` then `make dev` is the whole cold-start.
.DEFAULT_GOAL := help
.PHONY: help setup dev api web db test check

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## One-shot cold start: deps (modern + harness), env file, local Postgres
	uv sync
	uv sync --project harness
	pnpm install
	cp -n .env.example .env.local || true
	docker compose -f infra/compose.yml up -d
	@echo "Setup complete. Run 'make dev' to start the API + web."

db: ## Start local Postgres (localhost:5432; no cloud, no SQLite fallback)
	docker compose -f infra/compose.yml up -d

api: ## FastAPI backend on :8000
	uv run uvicorn capychem.api.main:app --reload

web: ## Next.js frontend on :3000
	pnpm --filter web dev

dev: ## API + web together (Ctrl-C stops both)
	@echo "Starting API (:8000) and web (:3000)…"
	uv run uvicorn capychem.api.main:app --reload & \
	pnpm --filter web dev; \
	kill %1 2>/dev/null || true

test: ## Backend + web test suites (needs Postgres + harness venv)
	uv run pytest
	pnpm --filter web test

check: ## All gates: mypy, ruff, web typecheck + lint
	uv run mypy -p capychem -p capychem.api
	uv run ruff check .
	pnpm --filter web typecheck
	pnpm --filter web lint
```

- [ ] **Step 4: Verify the Makefile parses and non-destructive targets work**

Run:
```bash
make help
make db && docker compose -f infra/compose.yml ps
```
Expected: `help` lists targets; `db` brings up Postgres (or reports already-running). Do **not** run `make setup` end-to-end here (it re-syncs everything) unless verifying a clean clone.

- [ ] **Step 5: Confirm `cp -n` guard doesn't clobber**

Run: `make setup 2>/dev/null; git status --porcelain .env.local`
Expected: `.env.local` is untouched (it's gitignored anyway) — the `cp -n` skipped it because it exists.

- [ ] **Step 6: Commit**

```bash
git add Makefile .nvmrc package.json
git commit -m "feat(dx): make setup/dev + Node 22 pinning — one-command cold start"
```

---

## Task 5: README fork-and-run polish

Correct the honest-but-stale friction points from the runbook table (rows 4-6) and point at `make`. **Keep every honesty caveat** — the in-silico banner, 21-comparable figure canon, single-seed disclaimers all survive verbatim.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Locate the setup/quickstart section**

Run: `grep -n "uv sync\|alembic\|Langfuse\|langfuse\|## \|pnpm install\|docker compose" README.md`
Read the surrounding quickstart block.

- [ ] **Step 2: Add the `make setup` / `make dev` path**

At the top of the quickstart, add the one-command path (keep the explicit long-form steps below it for readers who want to see what runs):

```markdown
### Quick start

```bash
git clone <repo> && cd CapyChem
make setup   # deps (modern + harness) · .env.local · local Postgres
make dev     # API on :8000 + web on :3000
```

`make setup` is the whole cold start; the explicit steps it runs are below if you'd
rather do them by hand. Requires Python 3.12 + `uv`, Docker (for Postgres), and Node 22 +
pnpm 11.5.0. The harness's Python 3.10 is fetched automatically by `uv` — you don't
install it.
```

- [ ] **Step 3: Mark alembic redundant, Langfuse optional, add the two notes**

Apply these corrections in the quickstart/notes prose (exact wording may adapt to surrounding text, but the *content* is required):

- Where `alembic upgrade head` appears: annotate it "**(redundant if you start the API — migrations auto-run on boot)**".
- Where Langfuse setup appears: annotate it "**(optional — tracing only; the app runs fully without it)**".
- Add a one-liner near the harness/Python note: "The harness needs Python 3.10, which `uv` fetches automatically."
- Near the test instructions: "`uv run pytest` (\"Test all\") needs a running Postgres **and** the harness venv — some API tests error rather than skip without them."

- [ ] **Step 4: Verify no honesty caveat was dropped**

Run: `grep -n "in-silico\|21 comparable\|no claim\|efficacy\|single-seed\|excluded for cause" README.md`
Expected: the in-silico banner and figure-canon language are still present and unchanged.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: fork-and-run README polish (make path, alembic/Langfuse/harness/pytest notes)"
```

*(If Task 3 wasn't committed separately, its `CLAUDE.md` edit rides here.)*

---

## Task 6: Fix the Compare fixture so the beat-GA shot shows a real verdict

`COMPARE_PAYLOAD.b` is currently exploratory run **269**, so `CompareView`'s `Verdict` guard (`a.task === b.task && a.mode === "benchmark" && b.mode === "benchmark"`, `CompareView.tsx:144-145`) correctly renders the amber "not directly comparable" banner. Repoint `b` at run **268** — which is *already* a benchmark/graph_ga row in `RUNS_LIST` (best 0.7719, troglitazone) — so it stays consistent across surfaces (resolving the fixture author's "no run_id with two mode badges" warning) and yields the green verdict "Run 281 leads by 0.1095 · both benchmark". `0.8814 − 0.7719 = 0.1095`.

**Files:**
- Modify: `apps/web/e2e/_fixtures.ts` (`COMPARE_PAYLOAD.b`)
- Modify: `apps/web/e2e/compare-shot.spec.ts` (URL + assert verdict)

**Interfaces:**
- Produces: `COMPARE_PAYLOAD` where both `a` and `b` are `mode: "benchmark"`, same task, so `Verdict` renders the green leads-by readout with "no analyzer step" on the GA column.

- [ ] **Step 1: Update the compare-shot spec to assert the green verdict (failing first)**

In `apps/web/e2e/compare-shot.spec.ts`, change the navigation URL and add a verdict assertion after the existing `"no analyzer step"` wait:

```typescript
    await page.goto("/compare?a=281&b=268", { waitUntil: "networkidle" });
    await page.getByText("Two runs, side by side").waitFor({ timeout: 15_000 });
    await page.getByText("no analyzer step").waitFor({ timeout: 5_000 });
    await page.getByText(/leads by/).waitFor({ timeout: 5_000 });   // green both-benchmark verdict
```

- [ ] **Step 2: Run the compare shot to confirm it fails on the verdict wait**

Run: `SHOT_DIR=/tmp pnpm --filter web exec playwright test e2e/compare-shot.spec.ts`
Expected: FAIL — times out on `/leads by/` because `b` (269) is still exploratory → amber "not directly comparable".

- [ ] **Step 3: Repoint `COMPARE_PAYLOAD.b` at run 268 (benchmark GA)**

In `apps/web/e2e/_fixtures.ts`, replace the `b:` object (and its stale comment) in `COMPARE_PAYLOAD` with run 268, consistent with its `RUNS_LIST` row:

```typescript
  // b is run 268 — the same benchmark Graph-GA row that appears in RUNS_LIST (same mode
  // badge everywhere). Both runs are benchmark + same task, so Verdict draws the honest
  // head-to-head: 281 (with an analyzer step) leads the GA control by 0.1095. The GA
  // column shows "no analyzer step" because a Graph-GA run carries no hypotheses.
  b: {
    run_id: 268,
    task: "troglitazone_rediscovery",
    mode: "benchmark",
    status: "exhausted",
    best_score: 0.7719,
    oracle_calls: 10000,
    budget: 10000,
    cost_so_far_usd: 0.4188,
    top_k: [
      { smiles: "O=C(Nc1ccc(Cl)cc1)c1ccc2[nH]ncc2c1", score: 0.7719 },
      { smiles: "Cc1ccc(Nc2ncnc3sccc23)cc1", score: 0.7514 },
      { smiles: "COc1ccc(Nc2ncnc3cccc23)cc1", score: 0.7331 },
    ],
    hypotheses: [],
  },
```

Leave `a` (281) and `auc_overlay` unchanged (overlay `b` values already end at 0.7719).

- [ ] **Step 4: Run the compare shot to confirm it passes**

Run: `SHOT_DIR=/tmp pnpm --filter web exec playwright test e2e/compare-shot.spec.ts`
Expected: PASS — "no analyzer step" and "leads by" both present, no h-scroll.

- [ ] **Step 5: Confirm the CompareView vitest suite is still green**

Run: `pnpm --filter web test -- --runTestsByPath app/compare/CompareView.test.tsx`
Expected: PASS. If a case pinned the old exploratory-`b` "not comparable" default, update *that case* to construct its own exploratory payload rather than relying on the demo default — do not weaken the guard. Keep at least one test that still exercises the amber not-comparable path (construct it inline).

- [ ] **Step 6: Commit**

```bash
git add apps/web/e2e/_fixtures.ts apps/web/e2e/compare-shot.spec.ts apps/web/app/compare/CompareView.test.tsx
git commit -m "test(web): compare fixture pairs 281 vs GA-268 so the beat-GA verdict renders"
```

---

## Task 7: Add the WS-replay fixture + `snapshotById` routing

The mock WebSocket (`stubWebSocket`) opens with no traffic, so the cockpit never ticks. Add `stubWebSocketReplay` that fires `onopen`, then replays a scripted `RunEvent` list on a timer — driving `LiveRun.onmessage → applyEvent` so the cockpit climbs, live, with **zero backend**. Also add `snapshotById` so a single `mockApi` call can serve different snapshots to `/runs/284`, `/runs/281`, `/runs/271` across one video.

**Honesty:** the replay drives run **284** (the real *running* row) and its scripted trajectory stays **below** the Graph-GA baseline (0.7712), ending at the true `SNAPSHOT_RUNNING` state (top10_mean 0.7431 @ 4200/10000 calls). The cockpit's baseline readout honestly shows "behind by 0.028 — still 5,800 calls to go." Nothing claims a live beat; the beat lives in the Compare shot (Task 6).

**Files:**
- Modify: `apps/web/e2e/_fixtures.ts`
- Consumes (verify shapes, don't change): `apps/web/lib/runEvents.ts` `RunEvent`, `apps/web/app/runs/[id]/LiveRun.tsx`.

**Interfaces:**
- Produces:
  - `stubWebSocketReplay(page: Page, events: unknown[], stepMs?: number): Promise<void>`
  - `SNAPSHOT_REPLAY_START` — a `running` snapshot for run 284 at the cold/early state with `graph_ga_baseline: 0.7712`.
  - `DEMO_REPLAY_EVENTS` — an ordered `RunEvent[]` (generation.complete ×N + one analyzer.hypothesis) climbing to top10_mean 0.7431 @ 4200 calls.
  - `MockOpts.snapshotById?: Record<number, unknown>` consumed by `mockApi`.

- [ ] **Step 1: Confirm the cold-start snapshot fields**

Run: `sed -n '/export const SNAPSHOT_COLD/,/};/p' apps/web/e2e/_fixtures.ts`
Note whether it has `status: "running"` and a `graph_ga_baseline`. `SNAPSHOT_REPLAY_START` (next step) must have `status: "running"` and `graph_ga_baseline: 0.7712` so the socket opens and the baseline delta renders during the climb.

- [ ] **Step 2: Add `SNAPSHOT_REPLAY_START` and `DEMO_REPLAY_EVENTS`**

In `apps/web/e2e/_fixtures.ts` (after `SNAPSHOT_RUNNING`), add. Reuse `HYPS` already defined in the file. Adjust field names to match `RunSnapshot` (mirror `SNAPSHOT_RUNNING`'s exact keys):

```typescript
// The starting frame for the deterministic "live" cockpit beat (demo.spec.ts): run 284
// at an early generation, socket open, first results not in yet. graph_ga_baseline is set
// so the baseline delta renders honestly as the climb proceeds. Same key set as
// SNAPSHOT_RUNNING so the cockpit renders identically.
export const SNAPSHOT_REPLAY_START = {
  ...SNAPSHOT_RUNNING,
  generation_index: 2,
  oracle_calls_used: 800,
  best_score: 0.64,
  top_k: SNAPSHOT_RUNNING.top_k.map((m, i) => ({ ...m, score: m.score - 0.10 + i * 0.01 })),
  auc_curve: [
    { oracle_calls: 100, top10_mean: 0.41 },
    { oracle_calls: 800, top10_mean: 0.64 },
  ],
  cost_so_far_usd: 0.31,
  hypotheses: HYPS.slice(0, 1), // the gen-1 hypothesis is already in; gen-8 arrives live
};

// Scripted RunEvents (shapes = lib/runEvents.ts RunEvent). Emitted one per `stepMs` by
// stubWebSocketReplay so the cockpit visibly ticks. Every top10_mean stays BELOW the
// Graph-GA baseline 0.7712 — the beat is NOT claimed here (see the Compare shot). Ends at
// the true SNAPSHOT_RUNNING state (0.7431 @ 4200).
export const DEMO_REPLAY_EVENTS = [
  { type: "generation.complete", generation_index: 4, best_score: 0.70, top10_mean: 0.70,
    oracle_calls_used: 1600, cost_so_far_usd: 0.52, top_k: SNAPSHOT_RUNNING.top_k },
  { type: "generation.complete", generation_index: 6, best_score: 0.726, top10_mean: 0.726,
    oracle_calls_used: 2800, cost_so_far_usd: 0.74, top_k: SNAPSHOT_RUNNING.top_k },
  { type: "analyzer.hypothesis", after_generation_index: 8, text: HYPS[1].text,
    structured_json: HYPS[1].structured_json },
  { type: "generation.complete", generation_index: 10, best_score: 0.7431, top10_mean: 0.7431,
    oracle_calls_used: 4200, cost_so_far_usd: 1.0362, top_k: SNAPSHOT_RUNNING.top_k },
];
```

- [ ] **Step 3: Add `stubWebSocketReplay`**

After `stubWebSocket` in `_fixtures.ts`:

```typescript
// Like stubWebSocket, but replays a scripted event list on a timer so the cockpit ticks
// deterministically with NO backend. Only the app's /ws/runs/ socket is faked; all other
// WebSocket URLs (Next HMR) delegate to native. Events serialize into the page via the
// addInitScript arg. The first event fires after `stepMs`, leaving the cold-start frame
// visible briefly before results arrive.
export async function stubWebSocketReplay(page: Page, events: unknown[], stepMs = 1100) {
  await page.addInitScript(
    ({ events, stepMs }) => {
      const Native = window.WebSocket;
      function Fake(this: unknown, url: string, protocols?: string | string[]) {
        if (typeof url === "string" && url.includes("/ws/runs/")) {
          const ws = {
            readyState: 1,
            onopen: null as null | ((ev: Event) => void),
            onmessage: null as null | ((ev: MessageEvent) => void),
            onclose: null as null | ((ev: Event) => void),
            onerror: null,
            send() {},
            close() {
              (this as { readyState: number }).readyState = 3;
            },
            addEventListener() {},
            removeEventListener() {},
          };
          setTimeout(() => ws.onopen?.(new Event("open")), 0);
          (events as unknown[]).forEach((ev, i) => {
            setTimeout(
              () => ws.onmessage?.({ data: JSON.stringify(ev) } as MessageEvent),
              (i + 1) * stepMs,
            );
          });
          return ws;
        }
        return new Native(url, protocols);
      }
      Fake.CONNECTING = 0;
      Fake.OPEN = 1;
      Fake.CLOSING = 2;
      Fake.CLOSED = 3;
      Fake.prototype = Native.prototype;
      // @ts-expect-error override the global for the capture only
      window.WebSocket = Fake;
    },
    { events, stepMs },
  );
}
```

- [ ] **Step 4: Add `snapshotById` to `MockOpts` and `mockApi`**

In the `MockOpts` type, add:

```typescript
  // Serve a different snapshot per run id (a single mockApi call across a multi-run video).
  snapshotById?: Record<number, unknown>;
```

In `mockApi`, change the `/runs/{id}` branch:

```typescript
    else if (/^\/runs\/\d+$/.test(p)) {
      const id = Number(p.split("/")[2]);
      body = opts.snapshotById?.[id] ?? opts.snapshot ?? SNAPSHOT_COMPLETED;
    }
```

- [ ] **Step 5: Typecheck the fixtures**

Run: `pnpm --filter web typecheck`
Expected: PASS (no type errors in `_fixtures.ts`). Fix any key mismatches against `RunSnapshot`/`RunEvent`.

- [ ] **Step 6: Commit**

```bash
git add apps/web/e2e/_fixtures.ts
git commit -m "test(web): WS-replay stub + snapshotById + honest replay trajectory for the demo"
```

---

## Task 8: Write `demo.spec.ts` — the video click-through

One `test` that walks the 13-shot storyboard as a single video. Video is enabled per-file (not globally, so the a11y/shot specs stay video-free). All selectors below are verified against the existing `*-shot.spec.ts` files. Dwell timings give the GIF room to breathe.

**Files:**
- Create: `apps/web/e2e/demo.spec.ts`

**Interfaces:**
- Consumes: `mockApi`, `stubWebSocketReplay`, `forceDark`, `SNAPSHOT_COLD` *(or `SNAPSHOT_REPLAY_START`)*, `SNAPSHOT_REPLAY_START`, `DEMO_REPLAY_EVENTS`, `SNAPSHOT_COMPLETED`, `SNAPSHOT_EXPLORATORY`, `MANIFEST_EXPLORATORY`, `RESOLUTION_MATCH`, `RESOLUTION_NOMATCH`, `RUNS_LIST` from `_fixtures.ts`.

Storyboard → route → fixture → key selector (verified):

| # | Route | Fixture | Verified anchor |
|---|-------|---------|-----------------|
| 1-2 | `/` | `runs: RUNS_LIST` | `getByText("The loop")` |
| 3 | `/launch` | `resolution: RESOLUTION_MATCH` | pick `troglitazone_rediscovery` → `"Resolved plan"` |
| 4 | `/launch` | `resolution: RESOLUTION_NOMATCH` | `getByLabel("Describe what you want")` → `Resolve` → `"No benchmark matches that objective"` |
| 5-6 | `/runs/284` | `SNAPSHOT_REPLAY_START` + `stubWebSocketReplay(DEMO_REPLAY_EVENTS)` | cold frame → climb; dwell |
| 7 | `/runs/281` | `SNAPSHOT_COMPLETED` | `getByText("Analyzer reasoning")` |
| 8 | `/compare?a=281&b=268` | `COMPARE_PAYLOAD` | `"Two runs, side by side"`, `/leads by/`, `"no analyzer step"` |
| 9 | `/` | `RUNS_LIST` | benchmark strip pan |
| 10 | `/launch` | default | `Compose custom objective` → `Add term` → `Oracle for term` nth(1) `sa_score` |
| 11 | `/launch` | default | pick task → `Seed molecules` fill → `"3 SMILES parsed"` |
| 12 | `/runs/271` | `SNAPSHOT_EXPLORATORY` + `MANIFEST_EXPLORATORY` | `"Analyzer reasoning"`, `Download lineage (CSV)` |
| 13 | end | hold | — |

- [ ] **Step 1: Write `demo.spec.ts`**

Create `apps/web/e2e/demo.spec.ts`. Because a single `mockApi` route handler serves the whole run, install it once with `snapshotById`, and install the WS-replay stub before any navigation. Shots 5-6 are one continuous beat on `/runs/284`. Do **not** call `stabilizeForShot` on the live beat (it freezes motion).

```typescript
import { test, type Page } from "@playwright/test";
import {
  mockApi,
  stubWebSocketReplay,
  SNAPSHOT_REPLAY_START,
  DEMO_REPLAY_EVENTS,
  SNAPSHOT_COMPLETED,
  SNAPSHOT_EXPLORATORY,
  MANIFEST_EXPLORATORY,
  RESOLUTION_MATCH,
  RESOLUTION_NOMATCH,
  RUNS_LIST,
} from "./_fixtures";

// A single deterministic, backend-free video walking the storyboard. Recorded to
// test-results/**/video.webm (converted to docs/assets/demo.gif by the capture command in
// CLAUDE.md). Honest by construction: real historical oracle values, the live cockpit
// stays behind baseline (no live "beat"), every mode/in-silico guardrail is on screen.
test.use({
  viewport: { width: 1280, height: 800 },
  video: { mode: "on", size: { width: 1280, height: 800 } },
});

const dwell = (p: Page, ms: number) => p.waitForTimeout(ms);

test("demo click-through (launch → analyzer → beat-GA → compose → seeds → quality/export)", async ({
  page,
}) => {
  // One handler for the whole video: benchmark completed on 281, exploratory on 271, the
  // live-replay start on 284. The WS-replay drives 284 only (281/271 are terminal → no socket).
  await mockApi(page, {
    runs: RUNS_LIST,
    resolution: RESOLUTION_MATCH,
    manifest: MANIFEST_EXPLORATORY,
    snapshotById: {
      284: SNAPSHOT_REPLAY_START,
      281: SNAPSHOT_COMPLETED,
      271: SNAPSHOT_EXPLORATORY,
    },
  });
  await stubWebSocketReplay(page, DEMO_REPLAY_EVENTS, 1100);

  // Shots 1-2 — Overview: the loop, resting on Analyze (the differentiator).
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByText("The loop").first().waitFor({ timeout: 15_000 });
  await dwell(page, 1500);
  await page.getByText("The loop").first().scrollIntoViewIfNeeded();
  await dwell(page, 1800);

  // Shot 3 — Launcher: resolve a benchmark objective from the catalog.
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
  await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
  await dwell(page, 1600);

  // Shot 4 — FR-015 refusal: an objective with no benchmark is grounded + blocked (feature).
  await page.getByLabel("Describe what you want").fill("make it dissolve well in water");
  await page.getByRole("button", { name: /^Resolve$/ }).click();
  await page.getByText("No benchmark matches that objective").waitFor({ timeout: 5_000 });
  await dwell(page, 1800);

  // Shots 5-6 — Live cockpit: cold frame → analyzer hypothesis arrives → curve climbs,
  // honestly tracking the Graph-GA baseline (behind at gen 10). One continuous beat.
  await page.goto("/runs/284", { waitUntil: "networkidle" });
  await dwell(page, 800); // cold frame before the first replayed event
  // Let the scripted events play (4 events @ 1100ms + headroom).
  await dwell(page, 5500);

  // Shot 7 — Completed benchmark 281: the finished run beats the GA control (~0.11 AUC).
  await page.goto("/runs/281", { waitUntil: "networkidle" });
  await page.getByText("Analyzer reasoning").waitFor({ timeout: 15_000 });
  await dwell(page, 2200);

  // Shot 8 — Compare: honest head-to-head; 281 leads GA-268, GA has "no analyzer step".
  await page.goto("/compare?a=281&b=268", { waitUntil: "networkidle" });
  await page.getByText("Two runs, side by side").waitFor({ timeout: 15_000 });
  await page.getByText(/leads by/).waitFor({ timeout: 5_000 });
  await dwell(page, 2200);

  // Shot 9 — Overview benchmark strip (figure canon lives here).
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByText("The loop").first().waitFor({ timeout: 15_000 });
  await dwell(page, 1600);

  // Shot 10 — Compose a custom multi-term objective → flagged exploratory.
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Compose custom objective/ }).click();
  await page.getByText("Compose an objective").waitFor({ timeout: 5_000 });
  await page.getByRole("button", { name: /Add term/ }).click();
  await page.getByLabel(/Oracle for term/).nth(1).selectOption("sa_score");
  await dwell(page, 1800);

  // Shot 11 — Bring your own seeds; RDKit validates each server-side.
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
  await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
  await page.getByLabel("Seed molecules").fill("CCO\nc1ccccc1\nCC(=O)Oc1ccccc1C(=O)O");
  await page.getByText(/3 SMILES parsed/).waitFor({ timeout: 5_000 });
  await dwell(page, 1800);

  // Shot 12 — Exploratory run-detail 271: quality/trust read-out + lineage export.
  await page.goto("/runs/271", { waitUntil: "networkidle" });
  await page.getByText("Analyzer reasoning").waitFor({ timeout: 15_000 });
  await page.getByRole("link", { name: /Download lineage \(CSV\)/ }).waitFor({ timeout: 5_000 });
  await dwell(page, 2400);

  // Shot 13 — hold on the end frame.
  await dwell(page, 1500);
});
```

- [ ] **Step 2: Run the demo spec and confirm it produces a video**

Run: `pnpm --filter web exec playwright test e2e/demo.spec.ts`
Expected: PASS. Then confirm the artifact:
```bash
find apps/web/test-results -name "*.webm" -print
```
Expected: at least one `video.webm` under `apps/web/test-results/**`.

- [ ] **Step 3: Sanity-watch a couple of frames (optional but recommended)**

Extract a mid-run frame to eyeball the live cockpit is mid-climb and behind baseline:
```bash
WEBM=$(find apps/web/test-results -name "*.webm" | head -1); echo "$WEBM"
```
Keep the path for Task 9.

- [ ] **Step 4: Commit the spec (not the video yet)**

```bash
git add apps/web/e2e/demo.spec.ts
git commit -m "test(web): demo.spec.ts — deterministic 13-shot video click-through"
```

---

## Task 9: Produce and embed `docs/assets/demo.gif`

Install ffmpeg, convert the recorded `.webm` to a size-reasonable GIF, embed it at the top of the README (above the existing run-detail still), and document the capture command.

**Files:**
- Create: `docs/assets/demo.gif`
- Modify: `README.md` (embed at top)
- Modify: `CLAUDE.md` (Commands — capture command)

- [ ] **Step 1: Install ffmpeg**

Run: `brew install ffmpeg && ffmpeg -version | head -1`
Expected: prints an ffmpeg version.

- [ ] **Step 2: Convert `.webm` → `docs/assets/demo.gif` with a shared palette**

Two-pass palette keeps the GIF small and clean. From repo root:
```bash
WEBM=$(find apps/web/test-results -name "*.webm" | head -1)
ffmpeg -y -i "$WEBM" -vf "fps=13,scale=1280:-1:flags=lanczos,palettegen=stats_mode=diff" /tmp/demo-palette.png
ffmpeg -y -i "$WEBM" -i /tmp/demo-palette.png \
  -lc_filter "fps=13,scale=1280:-1:flags=lanczos" \
  -filter_complex "fps=13,scale=1280:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3" \
  docs/assets/demo.gif
ls -lh docs/assets/demo.gif
```
Expected: `docs/assets/demo.gif` exists. If it's larger than ~8–10 MB, drop to `fps=11` or `scale=1100:-1` and re-run. *(If the `-lc_filter` flag errors on your ffmpeg build, omit that line — the `-filter_complex` form is authoritative.)*

- [ ] **Step 3: Eyeball the GIF for honesty + legibility**

Open `docs/assets/demo.gif` and confirm, frame by frame:
- The live cockpit (shots 5-6) never shows a "beating baseline" claim — it reads "behind"/"tracking".
- The Compare shot shows "leads by 0.1095 · both benchmark" (not the amber banner).
- Exploratory shots (compose, run 271) show the `ModeBadge` "not benchmark-comparable".
- In-silico language is legible somewhere in the arc.
- No horizontal clipping at 1280px.

If any honesty issue appears, fix the fixture/dwell and re-record before continuing.

- [ ] **Step 4: Embed at the top of the README**

In `README.md`, immediately after the in-silico banner blockquote and before the existing `<p align="center"><img ... run-detail-full.png ...>` still, insert:

```markdown
<p align="center">
  <img src="docs/assets/demo.gif" alt="CapyChem demo: launch a benchmark objective, watch the analyzer reason and the score climb live, beat the Graph-GA control head-to-head, then compose a custom objective, bring your own seed molecules, and export lineage — all in-silico" width="820">
</p>

*~90-second tour (in-silico benchmark scores throughout): launch → the analyzer reasons each
generation → a finished run beats the strong Graph-GA control on this objective → compose a
custom multi-term objective (flagged exploratory) → bring your own seed molecules → per-candidate
quality read-out + lineage export. For the trace-level view, see [the Langfuse walkthrough](docs/langfuse-walkthrough.md).*
```

*(That trailing link is the handoff's "View trace → docs/langfuse-walkthrough.md" item — point viewers at the committed walkthrough rather than a live Langfuse recording.)*

- [ ] **Step 5: Document the capture command in CLAUDE.md**

In `CLAUDE.md` under Commands (near the other `pnpm --filter web` lines), add:

```markdown
Demo capture:
- `pnpm --filter web exec playwright test e2e/demo.spec.ts` — records the demo video to `apps/web/test-results/**/video.webm`
- Convert to GIF: `ffmpeg` two-pass palette → `docs/assets/demo.gif` (see `docs/superpowers/plans/2026-07-06-capychem-fork-run-polish-and-demo.md` Task 9 for the exact command)
```

- [ ] **Step 6: Commit**

```bash
git add docs/assets/demo.gif README.md CLAUDE.md
git commit -m "docs: committed demo.gif embedded at README top + capture command"
```

---

## Task 10: Full gate run + adversarial Critic pass

**Files:** none (verification only).

- [ ] **Step 1: Backend gates**

Run (Postgres + harness venv must be up):
```bash
uv run mypy -p capychem -p capychem.api
uv run ruff check .
uv run pytest
```
Expected: all green. (`pytest` includes the new `test_eval_cli_env.py`.)

- [ ] **Step 2: Web gates**

Run:
```bash
pnpm --filter web typecheck
pnpm --filter web lint
pnpm --filter web test
SHOT_DIR=/tmp pnpm --filter web exec playwright test e2e/a11y.spec.ts
SHOT_DIR=/tmp pnpm --filter web exec playwright test e2e/compare-shot.spec.ts e2e/demo.spec.ts
```
Expected: all green — including the axe WCAG-AA gate (`a11y.spec.ts`) and no h-scroll assertions.

- [ ] **Step 2b: Verify the `--no-dev` install claim end to end**

Run: `uv sync --no-dev && uv run --no-dev python -c "import capychem.proposer, httpx; print('no-dev ok')"; uv sync`
Expected: `no-dev ok`.

- [ ] **Step 3: Synchronous adversarial Critic**

Dispatch a **synchronous** `meta-plugin:agent-team-critic` (or `Explore`-style read-only) subagent with the diff of this branch and the acceptance criteria below. It must independently re-verify — do not trust builder claims. Feed it: the two acceptance blocks (A and B from the handoff), the Global Constraints above, and `git diff main...HEAD`. Ask specifically:
- Does any surface claim a live cockpit "beat" against behind-baseline data?
- Is the figure canon ever reduced to a bare fraction?
- Did any honesty caveat get dropped from the README?
- Does the `--no-dev` real-LLM path actually import now?
- Do all gates pass on a clean checkout of the branch?

Address any CONFIRMED finding before finishing. Re-run the affected gate after each fix.

- [ ] **Step 4: Finish the branch**

Use `superpowers:finishing-a-development-branch` to choose merge/PR. Do not push `origin` unless the user asks (main is already 22 commits ahead + unpushed).

---

## Self-Review (completed during authoring)

**Spec coverage:** Bundle A items 1-5 → Tasks 4/1/2/3/5. Bundle B items 1-4 → Tasks 6 (compare fixture) / 7-8 (WS-replay + demo.spec) / 9 (GIF + README + capture cmd + trace-link) . Acceptance A (frictionless clone, real-LLM path from install, no stale doc) → Tasks 1-5 + Task 10 Step 2b. Acceptance B (committed demo.gif telling the full arc, guardrails in-frame, web gates green) → Tasks 6-9 + Task 10 Step 2.

**Placeholder scan:** none — every code step shows complete code; the only deferred detail is confirming `SNAPSHOT_COLD`'s field set (Task 7 Step 1) and the exact README prose (content specified, wording adapts).

**Type consistency:** `stubWebSocketReplay(page, events, stepMs)`, `SNAPSHOT_REPLAY_START`, `DEMO_REPLAY_EVENTS`, `snapshotById` are defined in Task 7 and consumed with those exact names in Task 8. `RunEvent` shapes in `DEMO_REPLAY_EVENTS` match `lib/runEvents.ts` (`generation.complete` + `analyzer.hypothesis` fields). `load_local_env` matches the real `capychem.env` signature.
