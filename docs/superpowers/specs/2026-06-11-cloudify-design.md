# Cloudify (Slice 4 `03-cloudify`) — Design Spec

**Status:** Approved scope (4 design decisions confirmed 2026-06-11; sub-decisions a/b resolved by recommendation, pending user review of this written spec).
**Milestone:** `00-walking-skeleton`, slice 4 (final slice — shipping it closes the milestone). **Parent SPEC:** `../../../SPEC.md` §6.1, §6.3, §8.3. **Predecessor:** slice 3 `02-web-surface` (shipped).

## 1. Goal

Swap the QED oracle from a **local harness subprocess** to a **Modal-hosted worker**, proven end to end: a browser-driven QED run scores against the *deployed* Modal worker, with `RunCost.oracle_cost_usd` populated and a real-but-dormant cost gate. This exercises the last unproven seam of the walking skeleton (Modal) and closes the milestone.

## 2. Scope (confirmed decisions)

- **Migration scope — oracle scoring only.** Modal hosts `oracle.score`; the Graph-GA proposer stays a **local** subprocess. Oracle calls are the budget-accounted, expensive resource (PROJECT §10), and the Graph-GA proposer is replaced by the Modal **LLM** endpoint in milestone 02 — so moving it now is throwaway. (Trade-off: the API host still needs its local harness venv for proposing; full harness isolation is not a slice-4 goal.)
- **Oracle seam — env-selected backend; keep local.** Scoring routes through one interface with two backends chosen by `CAPYCHEM_ORACLE_BACKEND=local|modal` (default `local`). `local` = today's subprocess, unchanged; `modal` = the new worker. CI/pytest and dev-without-Modal use `local` and stay green with zero cloud dependency.
- **Scoring becomes async.** A new `score_batch_async` is awaited in the loop's score node — `local` wraps the subprocess in `asyncio.to_thread`, `modal` awaits `.remote.aio`. This also resolves the handoff's event-loop-blocking concern (WS ping gaps during sync scoring).
- **Minimal real cost gate now.** New `RunCost` table + live `oracle_cost_usd` accumulation + a dollar cap checked per generation in `runner.py`; over cap → clean termination with status `cost_capped` + a cost event over WS. Dormant on QED (CPU pennies) but genuinely exercised by a forced-tiny-cap test.
- **Real cloud run closes the slice.** Slice ships only when a browser-driven QED run scores via the *deployed* Modal worker end to end. Everything except the live cloud run stays locally verifiable via the `local` backend.

### Sub-decisions (resolved by recommendation; flag at review)
- **(a) Status value `cost_capped`** added to the SPEC §6.2 status set — a small, documented extension; clearer UI badge + test assertion than overloading `exhausted` (call-budget) or `stopped` (operator).
- **(b) Thin cost UI in this slice** — the slice-3 live view gains a `cost_so_far_usd` counter and a `cost_capped` status badge (slice 3 explicitly deferred "cost display" to slice 4). One number + the new terminal status; no new pages. Rich cost views remain milestone 04.

## 3. Non-goals (deferred)

- **LLM proposer / Modal LLM endpoint** (`llm.propose`, `llm.analyze`) → milestone 02/03. The worker hosts the oracle only.
- **Moving the Graph-GA proposer to Modal** → not this slice (throwaway; see §2).
- **Cost gate exposed in the launch form / configurable per run** → the cap is env/config-only for now (FR-001 plateau/cost knobs → milestone 04).
- **Rich cost views, run-list, compare, 2D structures** → milestone 04.
- **Alembic migrations** → still deferred; `RunCost` is a *new table*, handled by `metadata.create_all`. Alembic lands with the first ALTER of an existing table.
- **Strict pre-spend (mid-generation) gate enforcement** → boundary-stop is sufficient for a dormant scaffold (see §6).
- **Managed-Postgres picker, multi-task UI, auth** → later milestones.

## 4. Architecture

```
 apps/api (FastAPI, py3.12)                         apps/worker (Modal app, def in py3.12)
   runner.py ── loop.astream ──┐                      app.py:
                               │                        image = Image(py3.10)
   loop/graph.py: score node ──┤                              .pip_install(PyTDC 0.3.6 + harness deps + rdkit.six shim)
     await score_batch_async(smiles, task)                    .add_local_dir(harness/capychem_harness)
                               │                        @app.function() score(smiles, task):
   oracle.py backend-select    │  CAPYCHEM_ORACLE_BACKEND        # body runs in the 3.10 container
     local → to_thread(score_smiles)  ◀── unchanged              subprocess→ score.py (stdin/stdout JSON, unchanged)
     modal → Function.from_name("capychem-worker","score")
                .remote.aio(smiles, task) ───────────────────▶ deployed Modal worker (3.10 container)
```

- **The Modal container IS the legacy env.** The image is Python 3.10 with the harness deps; inside the remote function the worker shells out to the existing `harness/capychem_harness/score.py` **unchanged** — same stdin/stdout JSON contract, relocated into the container. Zero harness edits; one scoring code path. *(Alternative: refactor `score.py` to expose an importable `score()` core and import it in-container — rejected to avoid touching the pinned harness this slice.)*
- **`app.py` is modern py3.12 at definition time.** The PyTDC/harness import/exec happens only inside the remote function body (the 3.10 container), never at module top-level. This honors the CLAUDE.md rule "modern code never imports the harness" — a 3.10 Modal container is the legacy env materialized in the cloud, not modern code.
- **API → worker** via `modal.Function.from_name("capychem-worker", "score").remote.aio(...)`; the API process needs `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET` in env (env-only, never committed — CLAUDE.md critical constraint).

## 5. Components

### 5.1 `apps/worker/app.py` (standalone Modal app script; **not** a uv workspace member)
- `app.py` — Modal `App("capychem-worker")`; the `Image` definition (py3.10 + harness deps + `rdkit.six` shim + harness source); `@app.function() def score(smiles: list[str], task: str) -> list[dict]` returning `[{smiles, score, valid, wall_ms}]` (mirrors `OracleResult`, minus cost — cost policy stays modern-side). A `@app.local_entrypoint()` for `modal run`/manual smoke. The worker is "dumb": it scores, nothing else.
- **`modal` is added to `capychem-api`'s dependencies** (the API is the caller — `Function.from_name(...).remote.aio`). That puts `modal` in the workspace venv, so `modal run/serve/deploy apps/worker/app.py` works from it. Keeping `apps/worker` a plain script (no `pyproject.toml`, not a workspace member) avoids uv-build friction for a dir whose real deps live in the Modal `Image`, not the local env.

### 5.2 `packages/core/capychem/oracle.py`
- Keep `score_smiles(...)` (sync subprocess) **unchanged** — it becomes the named `local` backend primitive, so existing direct-call tests keep passing.
- Add `async def score_batch_async(smiles: list[str], task: str) -> list[OracleResult]` selecting the backend by `CAPYCHEM_ORACLE_BACKEND`:
  - `local` → `await asyncio.to_thread(score_smiles, smiles, task)` (cost `0.0`).
  - `modal` → `await Function.from_name(...).remote.aio(smiles, task)`, mapped to `OracleResult` with `cost_usd = (wall_ms/1000) * CAPYCHEM_ORACLE_USD_PER_SEC`.
- `OracleResult` gains `cost_usd: float = 0.0`. `CAPYCHEM_ORACLE_USD_PER_SEC` is a configured constant (placeholder default; **not** a real Modal price claim — PRD N6/cost-discipline framing).

### 5.3 `loop/graph.py` (slice 4 owns this; the "frozen since slice 2" note was a slice-3↔4 worktree guard)
- **score node:** `await score_batch_async(...)` instead of sync `score_smiles(...)`.
- **persist node:** set `OracleCall.compute_cost_usd = r.cost_usd` (currently left at the `0.0` default).
- **propose node untouched** (Graph-GA stays local/sync).

### 5.4 `runner.py` (the cost gate's home — handoff: "cost gate in runner.py")
- At each generation boundary (already detected via the growing `auc_curve`): `SELECT COALESCE(SUM(compute_cost_usd),0) FROM oracle_calls WHERE run_id=?` → upsert `RunCost(oracle_cost_usd, total_usd)` → include `cost_so_far_usd` in the `generation.complete` event.
- If `total_usd >= cap` (config default ~$50 via `CAPYCHEM_COST_CAP_USD`): set a `cost_capped` flag, break cooperatively (the existing astream boundary-stop mechanism — same as Stop), finalize `Run.status="cost_capped"`, broadcast `run.complete`. **Loop nodes need no gate logic.**
- The gate runs **runner-side**, so cost is aggregated from the DB (one cheap indexed query per generation) — no need to thread cost through `LoopState`.

### 5.5 Frontend (`apps/web/`, thin)
- The slice-3 live view (`/runs/[id]`) gains a small `cost_so_far_usd` counter (read from `generation.complete` / the `GET /runs/{id}` snapshot) and renders the `cost_capped` terminal status badge. No new routes/pages.

## 6. Data model

- **New table `RunCost`**: `id`, `run_id` (FK → `runs.id` ON DELETE CASCADE, unique), `llm_cost_usd` (default `0.0`), `oracle_cost_usd` (default `0.0`), `total_usd` (default `0.0`). New table → `metadata.create_all` creates it; **no Alembic** (no ALTER of an existing table).
- **`OracleCall.compute_cost_usd`** — already present (default `0.0`); slice 4 starts populating it. No schema change.
- **`Run.status`** — new value `cost_capped` (documented SPEC §6.2 enum extension).

**Cost-gate enforcement note (SPEC §8.3 reconciliation):** SPEC §8.3 phrases the gate as "projects past 1.5× the user's configured budget," but the configured budget is *oracle calls*, not dollars. Slice 4 implements the gate against a **dollar cap** (`CAPYCHEM_COST_CAP_USD`, default ~$50 = G2), which is the load-bearing intent; the "1.5× projection" refinement is deferred until there is real (LLM) cost to project (milestone 02).

## 7. Key flows

1. **Score (modal):** loop score node → `score_batch_async` → `fn.remote.aio` → Modal 3.10 container → subprocess `score.py` → results back → modal backend attaches `cost_usd` → persist writes `OracleCall.compute_cost_usd`.
2. **Cost gate:** runner sums cost at each boundary → upsert `RunCost` + emit `cost_so_far_usd` → over cap → `cost_capped` clean termination + `run.complete`.
3. **Local fallback:** `CAPYCHEM_ORACLE_BACKEND=local` → CLI + pytest score with zero Modal (today's behavior, now via `to_thread`), `cost_usd=0`.
4. **Cold start:** first `.remote.aio` may take ~30 s (DeepSeek-style cold start risk noted for the LLM later; oracle container is lighter) — the slice-3 WS heartbeat already keeps the socket open.

## 8. Alternatives considered

- **Oracle-only migration (chosen)** vs. **score + Graph-GA both on Modal.** Both makes the API host harness-free but adds a worker function that becomes throwaway once the milestone-02 LLM proposer lands. Chosen oracle-only for thinness and because oracle calls are the accounted resource.
- **Env-selected backend, keep local (chosen)** vs. **Modal-only + stub in tests.** Modal-only is one runtime path but forces every oracle-touching test onto a stub, requires Modal for dev, and breaks the no-cloud local CLI loop. Chosen the seam: existing suite needs zero Modal.
- **Subprocess→`score.py` inside the container (chosen)** vs. **import a refactored `score()` core in-container.** Import is marginally faster (no subprocess hop) but edits the pinned harness. Chosen subprocess: zero harness change, identical JSON contract relocated to the cloud.
- **Runner-side boundary-stop gate (chosen)** vs. **loop-side `stop_check` pre-spend gate.** Pre-spend is stricter but threads cost/cap through `LoopState` and the loop nodes (more invasive, fights the minimal-loop posture). Chosen runner-side: matches the handoff ("gate in runner.py"), reuses the existing cooperative-stop path, and is adequate for a dormant scaffold.
- **`cost_capped` status (chosen)** vs. **overloading `exhausted`.** Distinct status is a tiny enum extension but yields a clear UI badge and an unambiguous test assertion.

## 9. Testing

- **Unit (local backend, no Modal):** `score_batch_async` routes to `local` and returns `cost_usd=0`; the `CAPYCHEM_ORACLE_BACKEND` switch selects the right backend; the **cost gate fires** under a forced tiny `CAPYCHEM_COST_CAP_USD` → run ends `cost_capped` with `RunCost` populated; `RunCost` aggregation math (sum of `OracleCall.compute_cost_usd`).
- **Worker contract:** a test asserting the shape/typing of `score`'s return without deploying (guards the JSON contract the modal backend maps from). Modal's local-run/sandbox or a thin call into the harness scorer.
- **Integration (existing pattern):** the slice-3 REST/WS tests keep passing on the `local` backend; one test asserts `generation.complete` now carries `cost_so_far_usd`.
- **Manual / milestone-closing:** `modal serve apps/worker/app.py` dev smoke → `modal deploy` → browser QED run scores via the real worker; assert `RunCost.oracle_cost_usd > 0` and a Langfuse trace. Extend `scripts/smoke.sh` with a worker-import/app-build check.
- **Gates:** `uv run pytest`, `uv run mypy -p capychem -p capychem.api`, `ruff check`/`format`, `pnpm --filter web typecheck/lint/build/test` — all green on the `local` backend.

## 10. Exit criteria

- Browser-driven QED run completes end to end via the **deployed** Modal worker; `RunCost.oracle_cost_usd` populated; the `cost_so_far_usd` counter is visible live (SPEC G5 latency unaffected — async scoring removes the event-loop block).
- Cost gate verified by a forced-tiny-cap test → `cost_capped`.
- Full suite green on the `local` backend (CI needs no Modal).
- No harness `import` in modern (py3.12) `apps/`/`packages/` code; harness source executes only inside the 3.10 Modal container.
- Langfuse shows the nested per-run → per-generation → per-node trace (unchanged seam).
- Closes the `00-walking-skeleton` milestone exit criteria.
