# CapyChem Production v1 (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn CapyChem from a frozen benchmarked demonstrator into a polished, fork-and-run-locally, single-user in-silico lead/hit-optimization tool a computational chemist can drive against their own objective — production-grade first, objective-ownership second.

**Architecture:** No new services. All work sits inside the existing `packages/core` + `apps/api` + `apps/web` structure. Phase 1 is split into two milestones by the dependency graph: **06 production-hardening** (reopen-nothing hygiene/CI/a11y + reliability; no schema change except an enabling Alembic baseline) then **07 objective-ownership** (the pluggable oracle + composed objective + trust layer, all gated behind a visible benchmark/exploratory mode split so the shipped G1 claim stays pristine).

**Tech Stack:** Python 3.12 (uv + ruff + mypy + pytest), FastAPI, LangGraph, SQLAlchemy 2.0 async + Alembic (new), Postgres 16, RDKit, PyTDC 0.3.6 (isolated harness, Python 3.10, subprocess-only), Next.js 16 / React 19 / TypeScript / Tailwind / shadcn (vitest + Playwright + axe-core), Modal (optional), Langfuse.

## Global Constraints

Copied verbatim from the build handoff — every task's requirements implicitly include these:

- **N6 (in-silico only):** every score is an in-silico oracle score; NEVER claim real-world drug-discovery efficacy in code, copy, README, or docs. Defensible claim = *"a genuinely usable in-silico lead/hit-optimization tool a computational chemist could drive against their own scoring function."* Off-limits: "drug-discovery platform", "beats SOTA", "scientists use this".
- **Figure canon (never "21/23"):** beats/matches vanilla Graph-GA on all **21 comparable** PMO tasks (seed 42, 10k budget); **2 of 23 excluded-for-cause** (sitagliptin_mpo out-of-[0,1] oracle; valsartan_smarts oracle-semantic defect in the pinned env). No SOTA / multi-seed claim until Phase-2 multi-seed lands. Surfaces derive from the prose canon (2 excluded), NOT a naive `excluded_rows`-length read of `docs/04-compare-and-polish/g1-full23-10k-seed42.json` (whose `g1_verdict` says "1" because sitagliptin was pre-excluded upstream).
- **Benchmark-vs-exploratory mode split is the load-bearing invariant** — enforced in code + tests, not just docs. Any custom seed / custom oracle / composed objective / constraint / cross-run memory ⇒ `mode = exploratory`, never contaminates the G1 benchmark path. The eval harness only ingests `benchmark` runs.
- **Finishability is the binding risk** (near-free compute, <$50 TOTAL). No docking-in-loop, no GPU training, no auth/hosting. Finish 06 to full polish; 07 is the feature build. Phase 2 is out of scope.
- **Keep the analyzer differentiator central**; deepen it *with* the multi-term objective (per-component visibility) in 07/Phase-2.
- **Never `import` from `harness/`** — modern code calls it via subprocess + typed JSON only. Legacy env is pinned (PyTDC 0.3.6 / Python 3.10).
- **Validate every SMILES via RDKit before persistence.** Never trust LLM/operator output as valid.
- **Cost tracking is first-class:** every LLM and oracle call updates `RunCost`; `total_usd` sums both.

## Resolved open decisions (from spec §13)

- **OD-1:** cheap robustness patches (recoverable `paused` status + in-process durable resume rebuilt from Postgres rows). No durable-Modal-loop.
- **OD-2:** budget unit = **one unique candidate evaluation**, regardless of how many objective terms compose it (keeps the AUC-vs-oracle-calls currency identical to benchmark).
- **OD-3:** keep the flat env-tunable `$50` cap (`cost.py:16`, `CAPYCHEM_COST_CAP_USD`); reconcile SPEC §8.3 text to it.
- **OD-4:** quality gate = **annotate-only in benchmark mode** (top-10 stays comparable); per-run hard-drop toggle allowed only in exploratory mode.
- **OD-5:** provenance must be **added** — harness JSON emits no version field today (`score.py:102`); model id is readable (`proposer.llm_model()`) but unpersisted. Both are net-new.
- **OD-6:** docking-as-rescore → Phase 2.
- **OD-7:** custom-oracle interface = Python-class plugin first (subprocess/REST contract is a Phase-2 follow-on).

---

## Verified code map (anchors for every task)

| Concern | Anchor (file:line) | State |
|---|---|---|
| Harness bridge | `packages/core/capychem/oracle.py:59` `score_smiles(smiles, task)` | subprocess+JSON; returns `OracleResult(.score: float\|None)`; no protocol/registry/metadata |
| Harness JSON contract | `harness/capychem_harness/score.py:102` `_emit({task, results, error})` | **no version field** (OD-5) |
| Model id | `packages/core/capychem/proposer.py:74-75` `llm_model()` | readable, **not persisted** |
| Unique-call budget (eval) | `packages/core/capychem/eval/runner.py:71,80,188` `mol_buffer` dict | authoritative dedup |
| Unique-call budget (product) | `packages/core/capychem/loop/graph.py:143-163` `mol_buffer` set | parallel impl; must stay byte-identical (G6) |
| Gen-0 seeding sink | `packages/core/capychem/loop/graph.py:48-50` | unconditional `_load_starting_pop`; **no operator-seed branch** (FR-001 sink) |
| Seed drop layers | `Launcher.tsx:126`, `schemas.py:12-28` `CreateRunRequest`, `run.py:16-26` `RunConfig`, `state.py:57-98` `LoopState` | no `seed_smiles` carrier anywhere |
| RNG seed (distinct!) | `run.py:20` / `graph.py:53` `seed + gen_index` | integer RNG seed — do NOT overload for seed SMILES |
| Cost gate | `packages/core/capychem/cost.py:16` `_DEFAULT_COST_CAP_USD=50.0`; `runner.py:223` reactive check | flat cap, env-tunable, post-generation |
| Authoritative AUC | `packages/core/capychem/eval/metric.py:16` `top_auc` | single-scalar, PMO-faithful; `loop/logic.py` curve is UI-only estimate |
| Verdict-guard idiom | `eval/verdict.py:22` + `eval/beat.py:22` `_PARSE_RATE_FLOOR=0.8` (duplicated); `valid_smiles_gate` in `loop/logic.py` | trust-gate home; de-dup into one module |
| Figure-canon source | `docs/04-compare-and-polish/g1-full23-10k-seed42.json`; prose `docs/05-operator-workbench/milestone.md:51` | 21 comparable + 2 excluded |
| Run status | `db/models.py:34` `status String(16)` (values incl. `cost_capped`,`max_generations`) | `paused` (6 chars) fits, no migration |
| Oracle-fault handling | `runner.py:229-233` catch-all `except Exception → errored` | no HarnessError branch, no degrade |
| Proposer fault pattern (to mirror) | `proposer.py:280-296` `asyncio.gather` fan-out + `TransientProposerError→empty`; `analyzer.py:162-166` degrade | oracle path has none |
| Modal propose n>1 bug | `apps/worker/app.py:105-107` sends `n:n` (DeepSeek caps n=1; LATENT BUG comment) | port the `direct` gather fan-out |
| Startup sweep | `apps/api/capychem/api/main.py:39` orphan `running → stopped` | 06-06 flips to `paused`+resume |
| Migrations | none (`db/session.py:35` `create_all` + drop-recreate) | Alembic net-new (06-05) |
| CORS/WS origin | `apps/api/capychem/api/config.py:15` hardcoded; consumed `main.py:56` + `ws_runs.py:33` | make env-driven |
| Repo hygiene | no `LICENSE`, no `.github/workflows`, `.env.example` incomplete, `apps/web/README.md` = boilerplate | net-new |
| a11y | `globals.css:58/93` coral `--primary` fails 4.5:1 (3.57/3.28:1); `button.tsx:7` `ring-ring/50` ~1.7:1; no `aria-live`; swallowed catches `Overview.tsx:22/25`,`Launcher.tsx:56`,`CompareView.tsx:39`,`AppShell.tsx:67` | targeted remediation |

---

## File Structure

**Milestone 06 (production-hardening):**
- `LICENSE`, `CONTRIBUTING.md`, `apps/web/README.md` (rewrite), `README.md` (reframe), `.env.example` (complete) — docs/hygiene.
- `apps/api/capychem/api/config.py` — env-driven `ALLOWED_ORIGINS` (single source; `main.py` + `ws_runs.py` consume).
- `packages/core/capychem/cost.py` (docstring) + `SPEC.md §8.3` (reconcile) + `packages/core/tests/test_cost_gate.py` (guard test).
- `.github/workflows/ci.yml` — CI (backend + web + axe).
- `apps/web/app/globals.css`, `apps/web/components/ui/button.tsx`, `apps/web/components/workbench/AppShell.tsx`, `apps/web/components/workbench/ui.tsx`, `apps/web/app/runs/[id]/LiveRun.tsx`, `.../Cockpit.tsx`, `apps/web/app/{page,launch/page,runs/page,runs/[id]/page,compare/page}.tsx`, `apps/web/app/Overview.tsx`, `apps/web/app/launch/Launcher.tsx`, `apps/web/app/compare/CompareView.tsx`, `apps/web/app/runs/RunsBrowse.tsx` — a11y.
- `apps/web/e2e/a11y.spec.ts` — axe gate.
- `alembic.ini`, `packages/core/capychem/db/migrations/` — Alembic baseline; `db/session.py` startup wiring.
- `apps/api/capychem/api/runner.py`, `packages/core/capychem/loop/graph.py`, `apps/api/capychem/api/main.py`, `packages/core/capychem/resume.py` (new), `apps/worker/app.py`, `packages/core/capychem/proposer.py` — reliability.

**Milestone 07 (objective-ownership):**
- `packages/core/capychem/oracle/` (new package: `protocol.py`, `registry.py`, `pmo.py`, `descriptors.py`, `admet.py`), `objective.py` (composition+transforms), `constraints.py`, `quality.py`, `trust/gates.py` (extracted).
- `db/models.py` + Alembic revisions for `Run.mode`, `objective_json`, `constraints_json`, `seed_smiles`, `seed_source`, `manifest_json`, `Candidate` quality fields, `OracleCall.oracle_version`.
- `apps/api/capychem/api/{schemas,routes_runs,routes_catalog,intent}.py` — `mode`, `seed_smiles`, `/objective/validate`, `/runs/{id}/export.{csv,sdf}`, `/runs/{id}/manifest`, mode enforcement.
- `apps/web/app/launch/Launcher.tsx` + new objective-builder + seed-import components; `apps/web/components/workbench/ui.tsx` (quality badges + mode badge); `apps/web/lib/api.ts`.

---

## Milestone 06 — production-hardening (Tier 0 + reliability)

**Ordering rule:** 06-01→06-04 touch no schema and reopen nothing — ship first. 06-05 (Alembic) is the enabling gate for milestone 07. 06-06 needs no new column (paused fits `String(16)`; resume reconstructs from existing rows) so it can land independently.

### Task 06-01: Repo hygiene, fork-and-run docs, env-driven origins, cost-gate reconciliation

**Files:**
- Create: `LICENSE` (MIT — compatible with the modern dependency graph: RDKit BSD-3, PyTDC, FastAPI/Next MIT; the GPL `smina`/`mol_opt` legacy stack is subprocess-isolated in `harness/`, never linked or imported, so it does not infect the modern code's license).
- Create: `CONTRIBUTING.md` (dev setup, test commands, mode-split rule, N6 rule).
- Rewrite: `apps/web/README.md` (real app README, not create-next-app boilerplate).
- Modify: `README.md` (add the fork-and-run/objective-ownership framing from spec §9 **without** overwriting the honest G1 canon — 21/21-not-21/23, single-seed caveats, in-silico banner all survive).
- Modify: `.env.example` (add Modal tokens marked **OPTIONAL**, `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`, and the 5 undocumented `CAPYCHEM_*` vars: `CAPYCHEM_ANALYZER_BACKEND`, `CAPYCHEM_INTENT_BACKEND`, `CAPYCHEM_ORACLE_BACKEND`, `CAPYCHEM_ORACLE_USD_PER_SEC`, `CAPYCHEM_COST_CAP_USD`, plus new `ALLOWED_ORIGINS`; keep the `openssl rand -hex 32` line).
- Modify: `apps/api/capychem/api/config.py:15` — parse comma-separated `ALLOWED_ORIGINS` env (default `http://localhost:3000`).
- Modify: `SPEC.md §8.3` — replace the "rejects new generations when RunCost.total_usd projects past 1.5× the configured budget" sentence with the shipped reality: a flat, env-tunable (`CAPYCHEM_COST_CAP_USD`, default ~$50) absolute cap, checked after each generation, terminating the run as `cost_capped`.
- Modify: `packages/core/capychem/cost.py` docstring to match.
- Test: `packages/core/tests/test_cost_gate.py`, `apps/api/tests/test_cors_origins.py`.

**Interfaces:**
- Produces: `config.ALLOWED_ORIGINS: list[str]` (parsed from env), consumed unchanged by `main.py:56` CORS and `ws_runs.py:33` WS-origin check — one source.

**Acceptance:**
- `LICENSE`, `CONTRIBUTING.md` tracked; `apps/web/README.md` describes the actual app; `README.md` fork-and-run reframe preserves every honesty caveat (grep asserts "21 comparable" and no "21/23").
- Test: setting `ALLOWED_ORIGINS=https://a.com,https://b.com` makes both the CORS middleware and the WS origin check accept those origins and reject others (one parsed list drives both).
- Test: a run whose accumulated `RunCost.total_usd` crosses `cost_cap_usd()` terminates with status `cost_capped` and a persisted partial summary (documents-the-shipped-behavior guard).
- No code path implies pre-emptive/projective rejection anywhere.
- `uv run ruff check . && uv run mypy -p capychem -p capychem.api` clean on touched files.

### Task 06-02: CI pipeline (backend + web, free stub/graph_ga path)

**Files:**
- Create: `.github/workflows/ci.yml` — matrix: (a) Python job: `uv sync`, `uv run ruff check .`, `uv run mypy -p capychem -p capychem.api`, `uv run pytest` (with a Postgres service container or SQLite-in-memory per how tests bootstrap); (b) Web job: `pnpm install`, `pnpm --filter web lint`, `pnpm --filter web typecheck`, `pnpm --filter web test`. Runs on the free `CAPYCHEM_PROPOSER_BACKEND=stub` / `graph_ga` path (no DeepSeek/Modal keys).
- Modify: `README.md` — add the CI status badge.

**Acceptance:**
- Workflow file is valid YAML; jobs enumerate the exact commands above.
- No job requires a provider secret (stub/graph_ga only).
- **Axe gate is NOT added here** — it rides in 06-04 after a11y fixes land, so CI starts green.
- Verify locally that each command in the workflow actually runs green before committing the workflow (run them; capture output).

### Task 06-03: Accessibility remediation (WCAG AA at 1280px)

**Files:**
- Modify: `apps/web/app/globals.css` — darken `--primary` (light `:58`, dark `:93`) so white-on-coral clears **4.5:1** in both themes (anchor on the existing `active:bg-[#a9583e]` ≈ 5.06:1; keep hue 46 — darken L/C, do NOT swap the hue). Add a full-opacity focus token; decide the `text-primary`-as-normal-text accent policy (small coral body text currently 3.34:1 — either darken it too or reserve coral for ≥18px/large).
- Modify: `apps/web/components/ui/button.tsx:7` — focus from `ring-ring/50` to full-opacity ring (≥3:1).
- Modify: `apps/web/components/workbench/AppShell.tsx` — skip-to-content link + `id` on `<main>`; replace hand-rolled coral CTA text color if still failing.
- Modify: `apps/web/components/workbench/ui.tsx:39` — concise `MoleculeTile` alt (`molecule {n}, score {x}` style; drop the raw SMILES from alt).
- Modify: `apps/web/app/runs/[id]/LiveRun.tsx` + `Cockpit.tsx` — visually-hidden `aria-live="polite"` region announcing generation-complete/status/hypothesis summaries (NOT every batched candidate tick); `role="alert"` on error `<p>`s.
- Modify: `Overview.tsx:22/25`, `Launcher.tsx:56`, `CompareView.tsx:39`, `AppShell.tsx:67` — replace swallowed `.catch(()=>{})` with a small inline error/empty state.
- Modify: `RunsBrowse.tsx:149-163` — `aria-sort` on sortable header cells.
- Modify: 5 route files (`app/page.tsx`, `launch/page.tsx`, `runs/page.tsx`, `runs/[id]/page.tsx`, `compare/page.tsx`) — per-route `metadata`/`generateMetadata` titles.

**Acceptance:**
- OKLCH→sRGB contrast calc + manual check: primary button ≥4.5:1 both themes; focus ring ≥3:1; live/analyze/chart coral usages re-checked after the `--primary` change (identity preserved).
- Keyboard: skip link focusable first; runs-table sort announces state.
- Screen-reader: a completed generation announces once (politely); an API error announces via `role="alert"`.
- `pnpm --filter web typecheck && pnpm --filter web lint` clean.

### Task 06-04: axe-core CI gate

**Files:**
- Create: `apps/web/e2e/a11y.spec.ts` — Playwright + `@axe-core/playwright` across the 5 routes in **light + dark**, failing on serious/critical violations (seed a stub run so `/runs/[id]` renders).
- Modify: `.github/workflows/ci.yml` — add the axe job (now that 06-03 landed, it starts green).
- Modify: `apps/web/package.json` — `@axe-core/playwright` devDep + an `e2e:a11y` script if needed.

**Acceptance:**
- `pnpm --filter web exec playwright test a11y` passes locally against a running dev server on all 5 routes, both themes.
- CI job green.

### Task 06-05: Alembic baseline (enabling gate for milestone 07)

**Files:**
- Create: `alembic.ini`, `packages/core/capychem/db/migrations/env.py` + `versions/0001_baseline.py` — initial revision whose `upgrade()` exactly reproduces today's `create_all` schema (autogenerate against a fresh DB, then hand-verify no diff vs `metadata`).
- Modify: `packages/core/capychem/db/session.py` — startup runs `alembic upgrade head` (or `stamp` if already at baseline) instead of `create_all`; keep `create_all` only for ephemeral test DBs.
- Modify: `db/models.py:4-6` + `db/session.py:3-6` docstrings — retire the "drop/recreate, Alembic deferred" note.
- Modify: `CONTRIBUTING.md`/`README.md` — document `alembic upgrade head`.
- Add: `alembic` to `packages/core/pyproject.toml` deps.

**Acceptance:**
- On a DB born from the old `create_all` (no `alembic_version` table), the baseline `alembic stamp head` marks it current and a subsequent `upgrade head` is a no-op (does NOT try to re-create existing tables).
- On a fresh DB, `alembic upgrade head` builds the full current schema; `uv run pytest` passes against it.
- Autogenerate diff between the baseline revision and `Base.metadata` is empty.

### Task 06-06: Reliability patches (OD-1 cheap: pause + durable resume + oracle fault tolerance + Modal n>1)

**Files:**
- Modify: `apps/api/capychem/api/runner.py:229` — add a distinct `except HarnessError` in `_drive` that sets status `paused` + persists a partial `build_summary` (reuse the `cost_capped`/`stopped` fallback at `:246-271`), instead of falling into the catch-all `errored`.
- Modify: `packages/core/capychem/loop/graph.py:136-163` (score node) — catch a transient `HarnessError`/timeout and degrade to "skip this generation, keep budget, log + emit", mirroring `proposer.py:289-291`; ensure `stop_check` still observes no-progress so a persistent fault terminates (no spin).
- Create: `packages/core/capychem/resume.py` — `reconstruct_state(session, run_id) -> LoopState-seed` from persisted rows: `mol_buffer` = distinct scored `Candidate.smiles`; `calls_used` = its length; `gen_index` = `max(Generation.index)+1`; `population` = top `pop_size` by `(-score, smiles)` (matches `logic._sort_key`); effective hypothesis = last `AnalyzerHypothesis`; `auc_curve` recomputed by replaying generations in call order (the map flagged the curve is not persisted mid-run — recompute, don't reset, so FR-003 plateau still fires correctly).
- Modify: `apps/api/capychem/api/runner.py` — a resume entry that seeds `_drive`'s initial `LoopState` from `reconstruct_state` instead of the hardcoded zeroed state (`:144-162`).
- Modify: `apps/api/capychem/api/main.py:39` — startup sweep marks orphan `running → paused` (resumable), and auto-resumes (or exposes a retry).
- Modify: `apps/worker/app.py:105-117` — port `proposer.py:280-296` `asyncio.gather` single-`n` fan-out (per-index `seed+i`) + `TransientProposerError→empty` degradation into the worker `propose`; drop the `n:n` call and the even-usage split; optional warm-pool kwargs.
- Test: `packages/core/tests/test_resume.py`, `apps/api/tests/test_pause_recover.py`, `packages/core/tests/test_oracle_fault_tolerance.py`.

**Interfaces:**
- Produces: `resume.reconstruct_state(session, run_id) -> dict` consumed by `runner`'s resume path.

**Acceptance:**
- Test: a `HarnessError` during scoring → run goes `paused` (not `errored`) with a browseable partial summary; a resume rebuilds `mol_buffer`/`gen_index`/`population`/`auc_curve` from rows and continues to the same terminal state a crash-free run would reach (±budget accounting identical, G6-safe).
- Test: a transient scoring fault skips one generation, preserves budget, and a *persistent* fault still terminates (no infinite loop).
- Test: worker `propose(n=4)` returns 4 distinct-yet-deterministic candidates (fan-out), and a simulated 429 degrades to empty rows rather than crashing.
- `paused` handled everywhere a status string is branched (`run.py`, `logic.py`, `main.py`, web status filters).

---

## Milestone 07 — objective-ownership (Tier 1: make-it-yours + trust)

**Ordering rule:** 07-01 (mode) is the invariant carrier and must precede every feature that sets `mode=exploratory`. All schema changes go through Alembic revisions (06-05). Each feature ships with its mode-enforcement test.

### Task 07-01: Run.mode split + enforcement + UI badge + figure-canon fixture

**Files:**
- Alembic revision: `Run.mode` (`benchmark`|`exploratory`, default `benchmark`), `Run.objective_json` (nullable), `Run.constraints_json` (nullable).
- Modify: `db/models.py`, `run.py` (`RunConfig.mode`), `schemas.py` (`CreateRunRequest`/snapshot `mode`), `routes_runs.py` (refuse to tag `benchmark` if any exploratory feature present — API-level enforcement), `eval/*` ingestion (only `mode==benchmark` feeds `top_auc`/baselines).
- Create: `packages/core/capychem/figure_canon.py` — single source stating **21 comparable, 2 excluded** (derived from the g1 JSON but stating the prose canon), consumed by README/manifest/badges.
- Modify: `apps/web` — a prominent `benchmark`/`exploratory` badge on every run surface (Overview, RunsBrowse, LiveRun/Cockpit, Compare); exploratory carries "not benchmark-comparable".
- Test: `test_mode_enforcement.py` (a composed/custom/custom-seed run cannot be `benchmark`; benchmark path unchanged), a test that fails if any surface string prints `21/23`.

**Acceptance:** benchmark-mode eval reproduces committed G1 numbers unchanged (regression gate); the API rejects a `benchmark` tag on any exploratory-feature run.

### Task 07-02: FR-001 seed-SMILES plumbing (benchmark-safe; custom seed ⇒ exploratory)

**Files (the 6-layer fix, all required or the seed silently re-drops):**
- Alembic revision: `Run.seed_smiles` (nullable text/JSON), `Run.seed_source` (`default`|`custom`).
- Modify: `apps/web/lib/api.ts` `CreateRunBody` (+ `seed_smiles`), `Launcher.tsx:126-136` (include `plan.seed_smiles` in the `createRun` body).
- Modify: `schemas.py` `CreateRunRequest` (+ `seed_smiles: list[str] | None`), with an RDKit-validating field validator at the `/runs` boundary (a client can POST directly — do not rely on the intent-preview validation).
- Modify: `run.py` `RunConfig` (+ `seed_smiles`, `seed_source`), `create_run` Run insert.
- Modify: `loop/state.py` `LoopState` (+ seed-population key).
- Modify: `loop/graph.py:48-50` — gen-0 branch: when operator seeds present, build the population from them (RDKit-validated + canonicalized, GA-filled from the shipped pool or truncated to exactly `pop_size` — decide top-up so crossover keeps ≥2 parents) instead of `_load_starting_pop`.
- Modify: `loop/seeds.py` — a validate/canonicalize helper for operator seeds.
- Enforcement: any non-null `seed_smiles` ⇒ `mode=exploratory` (couples to 07-01).
- Test: `test_seed_plumbing.py` (operator seed reaches gen-0 population; invalid SMILES rejected at `/runs`; custom seed forces exploratory; RNG `seed` untouched).

**Acceptance:** a run launched with a pasted valid SMILES list starts gen-0 from exactly those molecules (top-up/truncate to `pop_size`), is tagged `exploratory`, and the integer RNG-seed reproducibility contract is unaffected.

### Task 07-03: Pluggable ScoringOracle protocol + registry + bundled presets

**Files:**
- Create: `packages/core/capychem/oracle/protocol.py` — `ScoringOracle` Protocol: `score(smiles: list[str]) -> list[float | None]` + metadata `name`, `version`, `direction` (`maximize`|`minimize`), optional `applicability_domain(smiles) -> float`.
- Create: `oracle/registry.py` — entry-point/plugin registry.
- Create: `oracle/pmo.py` — `PmoOracle(task)` wrapping the existing `score_smiles`/`score_batch_async` as the first registered impl (keep `OracleResult` internally; expose the protocol at the objective boundary). **Parity test:** identical scores to the current path.
- Create: `oracle/descriptors.py` — SA-score (RDKit `Contrib/SA_Score`), QED, MW/logP/TPSA as zero-new-dep oracles.
- Create: `oracle/admet.py` — ADMET-AI (optional dependency; import-guarded so the stub path never needs it).
- Thread `direction` into `logic.merge_and_truncate`/`_sort_key` and `top_auc` so a `minimize` oracle isn't silently inverted (default `maximize` = today's behavior).
- Any custom/non-PMO oracle ⇒ `mode=exploratory`.
- Test: `test_oracle_protocol.py` (registry round-trip, PMO parity, descriptor oracles, direction correctness).

**Acceptance:** the existing benchmark path routes through `PmoOracle` with byte-identical scores; a descriptor oracle scores a batch with no new dependency; direction is honored.

### Task 07-04: Objective composition engine + constraints

**Files:**
- Create: `packages/core/capychem/objective.py` — objective spec (`[{oracle, weight, transform}]` + aggregator `weighted_sum`|`weighted_product`) → **one scalar in [0,1]** (preserves AUC comparability by construction). Transforms: `sigmoid`, `double_sigmoid`/`step`, `reverse_sigmoid`, `value_map` (REINVENT4 parity).
- Create: `packages/core/capychem/constraints.py` — hard SMARTS include/exclude via RDKit `FilterCatalog` (PAINS/Brenk sets) applied at the validity gate (same path FR-005 uses); soft property-range bands (MW/logP/TPSA) as sigmoid/step components. A **constraint-starvation** signal distinct from FR-003 plateau ("no candidate satisfies constraints").
- Budget unit stays per-candidate (OD-2) even when free + costed terms mix.
- Modify: `routes_runs.py`/`intent.py` — accept an objective spec; `POST /objective/validate` previews the composite + what gets penalized.
- Any composed objective or constraint ⇒ `mode=exploratory`.
- Test: `test_objective.py` (each transform; weighted-sum/product in [0,1]; a single-term objective equals the raw oracle), `test_constraints.py` (SMARTS include/exclude; starvation ≠ plateau).

**Acceptance:** a 2-term composed objective produces a single [0,1] scalar, runs the loop, is tagged exploratory; constraint starvation surfaces distinctly from plateau.

### Task 07-05: Molecule-quality & trust layer

**Files:**
- Create: `packages/core/capychem/quality.py` — per-candidate SA-score/QED/Lipinski/Veber/PAINS/Brenk, computed at persistence time (bounded cost; all RDKit-native).
- Alembic revision: `Candidate` quality fields (or a linked `CandidateQuality`).
- Modify: `loop/graph.py` persist path (`:192-212`) — attach quality; `logic.build_summary` — run-level MOSES internal diversity (mean pairwise Tanimoto on Morgan FPs) + novelty vs seed into `summary_json` (JSON column, no migration).
- Create: `packages/core/capychem/trust/gates.py` — extract `_PARSE_RATE_FLOOR` (de-dup from `beat.py`/`verdict.py`) + `valid_smiles_gate` into one home; add the custom-oracle **canary** (score a fixed degenerate probe set before an exploratory run on a new plugin; warn on implausibly-high scores) and the OD-4 gate (annotate-only in benchmark; per-run hard-drop toggle in exploratory).
- Modify: `apps/web/components/workbench/ui.tsx` — quality badges on each top-K tile; diversity/novelty in the run summary.
- Test: `test_quality.py`, `test_trust_gates.py` (canary fires on degenerates; OD-4 toggle drops pre-oracle only in exploratory; benchmark top-10 unchanged).

**Acceptance:** every top-K candidate carries a quality report; benchmark top-10 is unchanged by the gate (annotate-only); the canary flags a known degenerate; the two `_PARSE_RATE_FLOOR` copies are unified.

### Task 07-06: Provenance / reproducibility manifest (OD-5)

**Files:**
- Modify: `harness/capychem_harness/score.py:102` — add `pytdc_version` (`tdc.version.__version__`) to the emitted JSON; mirror in `apps/worker/app.py`; parse it in `oracle.py`.
- Alembic revision: `Run.manifest_json` (git SHA, LLM model id from `proposer.llm_model()`, harness/PyTDC pin, Langfuse trace URL, config) and `OracleCall.oracle_version`.
- Modify: `run.py`/`runner.py` — populate the manifest at run start/finalize.
- Create: `GET /runs/{id}/manifest`.
- Test: `test_manifest.py` (harness emits a version string; manifest round-trips model id + PyTDC pin + git SHA).

**Acceptance:** a run exports a citable manifest with a real PyTDC version and model id; harness JSON carries the version field.

### Task 07-07: Lineage export (CSV/SDF)

**Files:**
- Create: `GET /runs/{id}/export.csv` and `.sdf` (full lineage: gen index, parent, hypothesis-at-birth, quality fields).
- Modify: `apps/web` run-detail — download buttons for CSV/SDF + the manifest.
- Test: `test_export.py` (CSV/SDF contain lineage + quality columns; SDF is RDKit-parseable).

**Acceptance:** a completed run exports a valid SDF (RDKit round-trips it) and a CSV with per-candidate lineage + quality.

### Task 07-08: Objective-authoring UI + seed-import UI + live improvements

**Files:**
- Create: objective-builder component (pick oracles + weights + transforms + SMARTS/property constraints, live preview via `/objective/validate`; collapses to the single-task pick in benchmark mode) + seed-import component (upload/paste SDF/SMILES/CSV, RDKit-validate at the boundary, show accepted/rejected).
- Modify: `Launcher.tsx`, `lib/api.ts`, `Cockpit.tsx` (analyzer per-component reasoning: which objective term moved; WS reconnect-with-backoff + "connection lost" state + cold-start "waking the model ~30s" copy).
- Test: vitest for the objective builder + import + quality display; extend the axe gate to the new surfaces.

**Acceptance:** a chemist can compose a 2-term objective with a constraint and paste a seed list entirely from the UI, see the exploratory badge, and launch; the cockpit announces per-component reasoning and survives a dropped socket.

---

## Self-Review

**Spec coverage:** §6.A→07-03; §6.B→07-04; §6.C→07-05; §6.D reliability→06-06, CI→06-02/04, cost-gate→06-01; §6.F migrations→06-05, columns→07-01/02/05/06; §6.G REST/export/manifest→07-04/06/07; §7.A→07-08; §7.B→07-02/08; §7.C→07-05; §7.D→07-07; §7.E a11y→06-03, WS/cockpit→07-08; §7.F mode/honesty→07-01, doc-scope→06-01; §9 DX→06-01/05; §11 honesty→06-01/07-01; §12 testing→each task's tests + 06-04 axe. Phase-2 items (§6.E, §7.G, SDK, multi-seed, docking, campaigns) intentionally deferred. **No gaps.**

**Placeholder scan:** every task names exact files + anchors + acceptance; no TBD/TODO. Per this project's convention (milestone plans stay high-level; per-slice TDD detail lives in the slice session), each task is sized to a reviewable slice with concrete files/interfaces/acceptance — the executing session writes the per-slice `docs/NN-*/NN-slice.md` with bite-sized TDD steps before touching code.

**Type consistency:** `mode`, `seed_smiles`/`seed_source`, `ScoringOracle.score`/`direction`, `objective_json`, `reconstruct_state`, `figure_canon`, `trust/gates.py` names are used consistently across the tasks that produce/consume them.
