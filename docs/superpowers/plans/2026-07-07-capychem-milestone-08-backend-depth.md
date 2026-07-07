# CapyChem Milestone 08 — Backend Systems Depth + Reframe — Execution Plan

> **For agentic workers:** This is a **milestone-level execution plan** executed by a **dynamic Workflow** in a fresh session (per the operator's autonomous-workflow choice). Per-slice fine-grained TDD is produced by the Workflow's Builder agents against each slice's acceptance criteria; this plan pins the slice contracts, sequence, gates, and the Workflow itself. Design spec: `docs/superpowers/specs/2026-07-07-capychem-backend-depth-and-reframe-design.md`.

**Goal:** Convert CapyChem's single-process, in-memory run execution into a durable Postgres-backed producer → queue → competing-consumer-worker system with a persistent oracle-score cache, backpressure, the missing REST-contract pieces, and ops maturity — then reframe the repo to lead with the backend engineering.

**Architecture:** All-in-Postgres. Durable queue via `SELECT … FOR UPDATE SKIP LOCKED` + lease/heartbeat/reclaim; out-of-process worker drives the existing LangGraph loop; cross-process live events via `LISTEN/NOTIFY`; a shared `OracleScoreCache` table; bounded concurrency. No Redis, no broker, no k8s. Runs on a single feature branch off `main`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async (asyncpg runtime / psycopg for Alembic), Alembic, Postgres 16, LangGraph, Langfuse, RDKit, pytest, mypy (strict), ruff. Build orchestrated by the Workflow tool.

## Global Constraints

Every task inherits these verbatim:

- **N6 — in-silico only.** Every score is an in-silico oracle score; never a real-world drug-discovery efficacy claim.
- **FIGURE CANON (verbatim for any benchmark claim; never a bare fraction):** "beats or matches Graph-GA on all 21 comparable PMO tasks · decisive on 9 · 2 of 23 excluded for cause (defective oracles, not losses) · bar ≥6/23".
- **All-Postgres.** No Redis / Kafka / RabbitMQ / Celery / k8s. The queue and event bus are Postgres.
- **Benchmark/exploratory mode wall preserved.** The G1 result and its data (`docs/04-compare-and-polish/g1-full23-10k-seed42.json`) are untouched. Docking / expensive oracles are NOT in committed scope (stretch only — §Slice 8).
- **Branch-first off `main`; ONE repo.** Branch `m08-backend-systems-depth`.
- **Gate-green before each slice ships:** `uv run ruff check .` · `uv run mypy -p capychem -p capychem.api` (strict) · `uv run pytest` · web `pnpm --filter web typecheck` · `eslint` · `vitest` · axe. mypy strict applies to all new code.
- **Validate every SMILES via RDKit before persistence.** Wrap every LangGraph node in a Langfuse span. Cost tracking is first-class (`RunCost.total_usd = oracle + llm`).
- **Re-verify every Builder claim** with an independent read-only Evaluator using REAL command output — do not trust a Builder's self-report (operator convention).
- **Never `import` from `harness/`;** cross the boundary only via the subprocess+JSON bridge.

---

## Slice sequence & dependency graph

```
S1 (green-on-clone + credibility) ──────────────┐  [independent; can run first, in parallel]
S2 (durable queue + out-of-proc worker) ── HARD GATE ──▶ S3 (LISTEN/NOTIFY events)
                                                  ├──▶ S4 (persistent oracle cache)
                                                  └──▶ S5 (backpressure + REST gaps)
S3,S4,S5 ──▶ S6 (ops: Dockerfile/compose/readyz) ──▶ S7 (reframe & docs) ── HARD GATE
S8 (docking) — STRETCH, uncommitted, do not build without re-approval
```

S2 is the foundation; S3/S4/S5 each depend only on S2 and could parallelize, but they touch overlapping files (`runner.py`, `ws_runs.py`, `graph.py`) — the Workflow runs them **sequentially** on the shared branch to avoid merge seams (no per-agent worktrees). S7 is last and packaging-heavy.

---

## Slice contracts

Each slice below is what the Workflow's Builder implements and the Evaluator gates. "Acceptance" = the behavioral checks + gate-green that must show real command output.

### Slice 1 — Green-on-clone + credibility  *(effort S, independent)*
**Files:** Create `apps/api/tests/conftest.py`; Modify `README.md`; Modify `docs/assets` references in `README.md`.
**Do:**
- `apps/api/tests/conftest.py` — skip (not error) the real-Postgres/real-harness integration tests when the DB or harness venv is absent, mirroring `packages/core/tests/conftest.py:26-29`. A bare `uv run pytest` must SKIP those, not ERROR.
- README results section — replace any bare-fraction phrasing with the **FIGURE CANON verbatim**; consolidate the ~20 scattered honesty hedges into one caveat box. Do not invent a wins/ties decomposition.
- Trim README GIF weight — keep 1 hero + `live-run.gif` inline; collapse the 5 `clip-*.gif` into a `<details>` block or links.
**Acceptance:** on a checkout with no Postgres/harness, `uv run pytest` reports SKIPs (0 errors) for the API integration suite; README results uses the canon verbatim; per-feature GIFs are behind `<details>`. Gate-green.

### Slice 2 — Durable job queue + out-of-process worker  *(effort L, THE CORE)* — **HARD HUMAN GATE after**
**Files:** New `apps/runner/` package (worker entrypoint + claim/lease logic) — a **new** process, distinct from the Modal `apps/worker`; Modify `apps/api/capychem/api/routes_runs.py` (`POST /runs` → enqueue); Modify `apps/api/capychem/api/runner.py` (`RunRegistry` → DB-as-source-of-truth); Modify `apps/api/capychem/api/db/models.py` + new Alembic revision under `apps/api/capychem/api/db/versions/`; Modify `apps/api/capychem/api/main.py` (drop the boot-time paused-sweep in favor of lease-expiry reclaim, or keep as a backstop).
**Interfaces (pin these names/types):**
- `models.Run` gains: `lease_owner: str | None`, `lease_expires_at: datetime | None`, `heartbeat_at: datetime | None`; status enum gains `"queued"`.
- `apps/runner`: `async def claim_next_run(session, *, worker_id: str, lease_ttl_s: int) -> int | None` (atomic `SELECT … FOR UPDATE SKIP LOCKED` over `queued`/expired-lease rows; returns claimed `run_id` or None); `async def renew_lease(session, run_id, worker_id, lease_ttl_s) -> None`; `async def release_run(session, run_id) -> None`.
- `routes_runs.create_run` path returns `{run_id, status: "queued"}`.
**Test strategy (Builder writes; Evaluator re-runs):** two concurrent workers + one queued run → exactly one drives it, no duplicate `Generation.index` (extends the existing double-resume-guard tests); a worker killed mid-run → its lease expires → a second worker reclaims and `reconstruct_state` reaches the same terminal state (extends `resume.py` determinism tests); `POST /runs` returns `queued` and does not `create_task`.
**Acceptance:** a run is driven end-to-end by a separate `apps/runner` process; kill it mid-run and a second runner finishes it; no double-execution under contention; the API process no longer drives loops. Gate-green. **STOP for human review before S3.**

### Slice 3 — Cross-process live events (`LISTEN/NOTIFY`)  *(effort M; depends S2)*
**Files:** Modify `apps/runner/` (emit events), `apps/api/capychem/api/ws_runs.py` (subscribe), possibly a small `apps/api/.../events.py` for the channel/payload contract.
**Do:** the worker, after persisting each generation event, issues `pg_notify(channel, payload)` (channel per run or a shared channel keyed by run_id); the API WS handler `LISTEN`s and fans out to subscribers on any replica. The existing "DB snapshot + replay for a run that never lived in this process" path becomes the normal path for late/reconnecting subscribers.
**Test strategy:** worker-process `NOTIFY` → API-process WS receives the event within budget (integration test, real Postgres, `aconnect_ws`, mirroring `apps/api/tests/test_api.py`); reconnect mid-run replays from DB snapshot then resumes live.
**Acceptance:** live WS updates work when the run is driven by a **different process** than the one serving the WS; new-generation → client < 2 s p95. Gate-green.

### Slice 4 — Persistent shared oracle-score cache  *(effort M; depends S2)*
**Files:** New `OracleScoreCache` model + Alembic revision; Modify the score path (`packages/core/capychem/oracle/__init__.py` and/or `loop/graph.py` score node) to consult the cache; Modify `objective.py` if the objective hash lives there.
**Interfaces:** cache key `(oracle_key: str, objective_key: str, canonical_smiles: str)` unique; `oracle_key` includes name+version (invalidation); `canonical_smiles` via RDKit canonicalization. Lookup before spending budget; on miss, score then write; a **hit costs $0 and is not counted** (preserve the slice-05 unique-call invariant `#OracleCall == calls_used`).
**Test strategy:** hit / miss / version-invalidation; two distinct SMILES strings for the same molecule resolve to the same cache entry (canonicalization); budget invariant holds with cache hits; cross-run sharing (run B reuses run A's scores).
**Acceptance:** re-scoring an identical molecule (same run or across runs) does not re-spend budget; hit-rate is observable (log/metric/Langfuse). Gate-green.

### Slice 5 — Backpressure + REST contract gaps  *(effort M; depends S2)*
**Files:** Modify `apps/runner/` (concurrency cap / max in-flight leases), `oracle/__init__.py` + `objective.py` (bounded executor around `to_thread`), `proposer.py` (bounded propose fan-out), `routes_runs.py` (pagination + idempotency).
**Do:** a global cap on concurrent runs per worker (semaphore / max leases); bounded pools replacing the unbounded default executor and the unbounded `asyncio.gather` propose fan-out; a `429`/`queued` intake response when at cap. `GET /runs` gains cursor+limit pagination (SPEC §6.3); `POST /runs` honors an `Idempotency-Key` header so a retry does not mint a duplicate.
**Test strategy:** intake beyond cap → `429`/`queued`; bounded pools never exceed the cap under a burst; pagination cursor is stable across inserts; a double `POST` with the same `Idempotency-Key` yields exactly one run.
**Acceptance:** concurrency caps enforced and observable; pagination + idempotency behave per contract. Gate-green.

### Slice 6 — Ops maturity  *(effort S–M; depends S2–S5)*
**Files:** Create `apps/api/Dockerfile`, `apps/runner/Dockerfile` (or one multi-target); Modify `infra/compose.yml` to stand up API + runner + Postgres; Modify `main.py` health routes; Modify `db/session.py` (`pool_pre_ping=True`).
**Do:** containerize the API and the runner; a compose target brings up the whole system; add `/readyz` (checks Postgres + queue reachability) distinct from `/healthz` (liveness); enable `pool_pre_ping`.
**Test strategy:** `docker compose up` → `/healthz` and `/readyz` green; a run enqueued via the containerized API is driven by the containerized runner.
**Acceptance:** the system stands up from `docker compose up`; `/readyz` reflects downstream health. Gate-green.

### Slice 7 — Reframe & docs  *(effort S–M; depends all)* — **HARD HUMAN GATE**
**Files:** Modify `README.md`; Create `docs/architecture.md`.
**Do:** move a tight **"Backend engineering"** highlights block to the first screen (queue/lease/reclaim, `LISTEN/NOTIFY`, persistent cache, backpressure, durable resume, subprocess isolation, real CI); add a 10-second ELI5 domain paragraph up top; reframe the tagline to "a durable, sample-efficient optimization / job-processing engine, demonstrated on molecular optimization." Write `docs/architecture.md`: run lifecycle (`POST /runs` → enqueue → lease → per-gen persist + `NOTIFY` → WS fan-out), the queue/lease protocol, the cache design, cost-gate enforcement, and a **"hard problems + tradeoffs I solved"** section (Postgres-as-queue vs a broker; cross-process live events; cache canonicalization/invalidation; crash-safe reclaim).
**Acceptance:** README leads with the backend within the first screen; the domain is ELI5-legible; `docs/architecture.md` covers the lifecycle + decisions; FIGURE CANON preserved verbatim; N6 intact. **This is judgment-heavy — human reviews the final framing.**

### Slice 8 — Docking on the worker pool  *(STRETCH — DO NOT BUILD without operator re-approval)*
Exploratory-mode Vina docking as the expensive workload that justifies the cache + exercises the pool under real load. HIV-1 protease (PDB 1HSG), receptor prepped once, `DockingOracle` via the pluggable registry, `direction="minimize"`. Only if S1–S7 land early. See spec §11.

---

## The dynamic Workflow (execution driver for the new session)

A single **resumable** Workflow, phases = slices. Autonomous between hard gates; every slice adversarially verified.

**Shape per slice:** `Builder → Evaluator → (repair once on FAIL) → Evaluator`. Builder implements against the slice contract + acceptance; Evaluator is read-only, re-runs the real gate commands + behavioral tests, and returns PASS/FAIL with command output. On FAIL, one Builder repair pass, then re-gate; still FAIL → the Workflow returns for the human.

**Hard gates (Workflow returns; human resumes via `resumeFromRunId`):** after **S2** (risky core) and before **S7** (packaging judgment).

**Isolation:** all agents work the **single `m08-backend-systems-depth` branch** — NO per-agent worktrees (slices share files and must compose). Builder commits at slice end after the Evaluator passes (frequent commits, gate-green). The new session's **orchestrator owns the milestone doc writes** (`docs/08-…/milestone.md` status flips, `handoff.md`, `log.md`) at each gate — not the Workflow agents.

**Skeleton** (the new session adapts + runs this; `agentType` uses the meta-plugin agent-team roles):

```js
export const meta = {
  name: 'm08-backend-depth',
  description: 'Build CapyChem milestone 08 (durable execution + cache + reframe) slice-by-slice with adversarial gates',
  phases: [
    { title: 'S1 credibility' }, { title: 'S2 queue+worker' }, { title: 'S3 events' },
    { title: 'S4 cache' }, { title: 'S5 backpressure+REST' }, { title: 'S6 ops' }, { title: 'S7 reframe' },
  ],
}

const SLICES = [ /* {key, title, contract, acceptance} per the slice contracts above */ ]
const HARD_GATE_AFTER = new Set(['S2', 'S6']) // return for human review after these

async function buildSlice(s) {
  let out = await agent(`Implement slice ${s.key}: ${s.contract}\nAcceptance: ${s.acceptance}\nCommit gate-green at the end.`,
    { label: `build:${s.key}`, phase: s.title, agentType: 'meta-plugin:agent-team-builder' })
  let verdict = await agent(`Independently verify slice ${s.key} against acceptance: ${s.acceptance}. Re-run ruff+mypy+pytest and the behavioral checks; return PASS/FAIL with real command output.`,
    { label: `verify:${s.key}`, phase: s.title, agentType: 'meta-plugin:agent-team-evaluator', schema: VERDICT })
  if (!verdict.pass) {
    await agent(`Repair slice ${s.key} to satisfy: ${verdict.failures}. ${s.acceptance}`,
      { label: `repair:${s.key}`, phase: s.title, agentType: 'meta-plugin:agent-team-builder' })
    verdict = await agent(`Re-verify slice ${s.key}: ${s.acceptance}. PASS/FAIL + evidence.`,
      { label: `reverify:${s.key}`, phase: s.title, agentType: 'meta-plugin:agent-team-evaluator', schema: VERDICT })
  }
  return { key: s.key, verdict }
}

const results = []
for (const s of SLICES) {                     // sequential: coupled files, must compose
  const r = await buildSlice(s)
  results.push(r)
  if (!r.verdict.pass) { log(`STOP: ${s.key} failed twice — human review`); return { results, stoppedAt: s.key } }
  if (HARD_GATE_AFTER.has(s.key)) { log(`HARD GATE after ${s.key} — returning for human review`); return { results, gateAfter: s.key } }
}
return { results, done: true }
```

Resume after a gate: `Workflow({ scriptPath, resumeFromRunId })` — passed slices replay from cache; the first uncached slice runs live.

---

## New-session start sequence (orchestrator)

1. `git checkout m08-backend-systems-depth` — the branch already exists off `main` with this plan + the design spec committed on it (created in the planning session). Confirm `git log --oneline -2`.
2. Synthesize `docs/08-backend-systems-depth/milestone.md` + `handoff.md` per `~/.claude/CLAUDE.md` (do NOT pre-create before this session). Update `docs/milestones.md` entry to `← active`.
3. Author the Workflow from the skeleton above (fill `SLICES` from the slice contracts), run it.
4. At each hard gate: review the diff, re-verify independently, flip milestone/handoff docs, then resume.
5. On milestone completion: gate-green, merge to `main`, mark shipped in `milestones.md`, write the next handoff.

---

## Self-review (done)

- **Spec coverage:** S1↔spec §4; S2–S6↔spec §5.1–5.6; S7↔spec §4+§6; data model↔spec §7; testing↔spec §8; slice list matches spec §9; docking-as-stretch↔spec §11. All covered.
- **Placeholders:** slice contracts carry acceptance criteria + pinned interface names; fine-grained TDD code is intentionally produced by the Workflow's Builders (milestone-altitude plan, per operator convention), not hand-written here.
- **Type consistency:** `claim_next_run/renew_lease/release_run`, the `Run` lease columns, and the `OracleScoreCache` key are referenced consistently across S2/S3/S4/S5.
