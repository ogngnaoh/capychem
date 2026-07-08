# Design Spec — Milestone 08: Backend Systems Depth + Reframe

**Status:** Draft (brainstormed 2026-07-07; awaiting review)
**Owner:** solo
**Related:** PRD.md · SPEC.md (§6.3, §7 Alt D, §9) · PROJECT.md §10 `[RE-DECIDE]` · docs/milestones.md (milestone 08, not yet synthesized)
**Supersedes:** the docking-first direction explored earlier this session (docking demoted from anchor → documented stretch; see §11).

---

## 1. Context & motivation

CapyChem is already an upper-tier intern portfolio project: real reliability engineering (generation-granular Postgres checkpointing, deterministic replay-based resume, a TOCTOU-correct double-resume guard, a transient-vs-config error taxonomy with bounded retry + graceful degradation), 397 tests with genuine Postgres+WebSocket+harness integration, mypy-strict, a non-token CI gate, clean hygiene.

Two things — verified against the code this session — keep it from reading as a *strong backend / distributed-systems* piece, which is the stated hiring target:

1. **Framing.** The README leads with "LLM-does-chemistry" and buries the genuine backend depth ~74% down the page under ~17 MB of autoplay GIFs. A 60-second backend-recruiter skim files it as a demo, not a systems project.
2. **The execution model is a single-process async monolith.** `RunRegistry` is documented `"""Owns the live runs. Single-process, single event loop (MVP)."""` with an in-memory `dict[int, RunHandle]`; runs are `asyncio.create_task` inside the FastAPI process; **all live run state lives in that dict.** Every "distributed-systems / caching-for-expensive-oracles" claim in PRD/SPEC/PROJECT is aspirational and absent in code (verified: no Dockerfile, no queue/broker, no persistent cache, `GET /runs` has no pagination).

This milestone closes both gaps. It is the honest resolution of PROJECT.md §10's `[RE-DECIDE]` ("the de-risked MVP is agentic/eval-heavy and backend-thin") — **make the backend genuinely load-bearing, then make it legible.**

## 2. Research basis (what this design optimizes for)

A fact-checked market research pass (deep-research, 102 agents, 3-vote adversarial verification) established what actually moves the needle for a big-tech backend intern portfolio in 2025-26. Design implications:

**Confirmed levers (build toward these):**
- Repo hygiene is the *gate* that decides dig-in-vs-bounce, but it is **not depth** — "valuable only when backed by actual depth." (CapyChem already clears the gate.)
- **One cohesive, production-like system beats volume.** Depth-over-breadth, especially for interns.
- **Cargo-cult architecture is a *negative* signal.** Prestige patterns adopted "for optics" count against you; a disciplined monolith earns most of the architectural credit. Build right-sized and *be able to defend the choice.*
- **A niche domain is only as strong as its legibility.** ELI5 the domain; quantify why it was needed and how much it helped.

**Refuted under verification (do NOT treat as differentiators — hygiene worth having, not levers that carry the project):** a live-deploy link materially raising odds; containers+CI/CD+monitoring being *itself* the depth signal; specific P95/coverage numbers being *the* production-grade tell.

**Net:** the win is not "add features" or "bolt on prestige infra." It is one genuine, defensible systems upgrade to the *existing* cohesive system, plus making its real depth legible.

## 3. Goals / non-goals

**Goals**
- G-08.1 — Convert run execution from an in-process asyncio monolith into a **durable, out-of-process producer/queue/competing-consumer system** whose crash-recovery is a real claim/lease (not a boot-time sweep), backed entirely by Postgres.
- G-08.2 — Ship the **persistent, shared oracle-score cache** the docs have promised since milestone 02, making "designed for expensive oracles" true rather than aspirational.
- G-08.3 — Add the resource-safety and API-contract table-stakes the audits flagged: bounded concurrency + backpressure, `GET /runs` pagination, `POST /runs` idempotency.
- G-08.4 — Ops legibility: Dockerfile(s) for `apps/api` + the worker, a compose that stands the whole system up, `/readyz` vs `/healthz`.
- G-08.5 — **Reframe** the repo to lead with the backend engineering, ELI5 the domain, and document the architecture + "hard problems I solved" narrative.
- G-08.6 — Every claim stays honest: the G1 PMO benchmark result is untouched and its FIGURE CANON is preserved; N6 holds.

**Non-goals**
- No Redis / Kafka / RabbitMQ / Celery / k8s (see §5.6 + §11 — deliberately rejected as cargo-cult at this scale).
- No multi-tenant / auth (PRD N8 stands).
- No docking / expensive oracle in the committed scope (documented stretch — §11).
- No new ML work; the loop's *behavior* is unchanged. This is an infrastructure milestone, not a product-features milestone.

## 4. Tier 0 — Reframe & harden (effort: S; partly now, finalized after Tier 1)

Presentation and credibility fixes. The pure-credibility items ship early (independent of Tier 1); the reframe/architecture docs land last so they describe the *real, post-Tier-1* architecture.

- **`uv run pytest` green on a bare clone.** Add `apps/api/tests/conftest.py` that *skips* (not errors) when Postgres/harness are absent, mirroring `packages/core/tests/conftest.py`. This is the single most awkward credibility item today (a green CI badge above a locally-failing suite).
- **Results framing.** Consolidate the ~20 scattered honesty hedges into one caveat box; lead the headline with the **FIGURE CANON verbatim** — "beats or matches Graph-GA on all 21 comparable PMO tasks · decisive on 9 · 2 of 23 excluded for cause (defective oracles, not losses) · bar ≥6/23" — rather than a bare fraction like "21/23". Do not invent any alternative decomposition of the wins/ties.
- **README weight + order.** Trim autoplay GIF weight (keep 1 hero + the live-run proof inline; collapse the 5 per-feature clips into `<details>`/links). Move a tight **"Backend engineering"** highlights block to the first screen: the producer/queue/worker execution model, Postgres-as-queue with lease/heartbeat/reclaim, `LISTEN/NOTIFY` live-event fan-out, the persistent oracle cache + budget, backpressure, durable resume, the subprocess isolation boundary, the real CI gate.
- **ELI5 the domain up top** — one paragraph a non-chemist backend reviewer parses in 10 seconds; chemistry framed as *the hard, real workload the system schedules and serves efficiently.*
- **`docs/architecture.md`** — the request/run lifecycle (`POST /runs` → enqueue → worker leases → per-generation persistence + `NOTIFY` → WS fan-out), the WS event schema, the queue/lease protocol, the cache design, cost-gate enforcement, and a **"hard problems + tradeoffs I solved"** section (the "what I learned" the research rewards): why Postgres-as-queue over a broker, cross-process live events, cache canonicalization/invalidation, crash-safe lease reclaim.

## 5. Tier 1 — Backend systems upgrade (effort: L, ~3–4 weeks)

The one genuine systems build. Every component is motivated by a real problem in the current design and is defensible without prestige infra.

### 5.1 Durable job queue + out-of-process worker (the core)
- **Producer:** `POST /runs` inserts the `Run` as `queued` (+ a job/lease row) and returns — it no longer `create_task`s the loop. Retry-safe via idempotency (§5.5).
- **Queue + competing consumers:** a separate **worker process** (`apps/runner/` or an `apps/worker` entrypoint) claims one queued run atomically with `SELECT … FOR UPDATE SKIP LOCKED`, drives the existing LangGraph loop, and renews a **lease/heartbeat** column while working. Multiple workers can run; work is distributed with no double-execution.
- **Real crash recovery:** a dead worker's lease expires; another worker reclaims the run and resumes from persisted generation state via the *existing* `reconstruct_state` replay. This replaces the boot-time `running→paused` sweep with a genuine claim/lease/reclaim protocol — and finally makes the durable-resume machinery a coherent story rather than a patch.
- **Source of truth flips to Postgres.** `RunRegistry`'s in-memory dict stops being authoritative; the DB is. The WS layer's already-present "DB-backed replay for a run that never lived in this process" path becomes the *normal* path.

### 5.2 Cross-process live events (Postgres `LISTEN/NOTIFY`)
- Decoupling execution breaks the current same-process WS→in-memory-state read. The worker emits each generation event by writing it (durably) and issuing `NOTIFY`; any API replica holding a WS connection is `LISTEN`ing and fans the event out to subscribers. Late subscribers get a DB snapshot + replay (already built).
- This keeps live-update latency within the PRD's <2 s p95 target without a separate message bus, and works across API replicas.

### 5.3 Persistent shared oracle-score cache
- New `OracleScoreCache` table keyed on `(oracle_name+version, task/objective hash, canonical_smiles) → score, wall_ms`. Consulted before spending budget; **shared across runs**; invalidated by oracle version.
- Correctness surface (good interview material): RDKit **canonicalization** of the key, **version-scoped invalidation**, and the budget invariant from slice 05 preserved — a cache hit costs $0 and (in exploratory mode) is not counted. Replaces/augments the per-run in-memory `mol_buffer` set with a durable, cross-run cache. This is the "caching/memoization for expensive oracles" the SPEC/PROJECT name and the code never had.

### 5.4 Bounded concurrency + backpressure
- A cap on concurrent runs per worker (max in-flight leases / semaphore); bounded pools around the oracle threads (`asyncio.to_thread` currently uses the unbounded default executor) and the propose fan-out (currently an unbounded `gather`); a `429`/`queued` response when the intake cap is hit. Demonstrates resource-exhaustion awareness — the first thing an interviewer probes after "what happens at 100 concurrent runs?"

### 5.5 REST contract gaps
- **Pagination** on `GET /runs` (cursor/limit — already promised in SPEC §6.3; currently unbounded `select(Run)` + per-row live lookup + Python-side sort).
- **`Idempotency-Key`** on `POST /runs` so a client retry doesn't mint a duplicate run (the enqueue must be idempotent).

### 5.6 Ops maturity
- **Dockerfile** for `apps/api` and the worker (SPEC §9 claims "containerized FastAPI"; none exists). A compose that stands up API + worker + Postgres together.
- **`/readyz`** (readiness) checking Postgres + queue reachability, distinct from `/healthz` (liveness, `SELECT 1`). Bundle `pool_pre_ping=True` on the async engine (managed Postgres drops idle conns).

**Deliberately NOT in Tier 1** (cargo-cult risk / scale not justified): Redis or a broker for the queue/events (Postgres suffices and is the defensible choice); horizontal API autoscaling infra; k8s/IaC beyond compose.

## 6. Framing pivot

Reposition the project (README, tagline, architecture doc) as a **durable, sample-efficient optimization / job-processing engine**, *demonstrated on* molecular optimization. Chemistry becomes the hard, real workload the system schedules and serves budget-efficiently — the means, not the headline. This is the ELI5-legibility the research demands and it puts the backend in front. The molecular-optimization product, benchmark, and analyzer all remain — they are the credible, non-toy workload that makes the systems work matter.

## 7. Data model changes

- `Run` (or a sibling `RunLease` row): add `lease_owner`, `lease_expires_at`, `heartbeat_at`, and a queue status (`queued`) to the existing status enum. Claim query orders queued runs and locks with `SKIP LOCKED`.
- `OracleScoreCache`: `(oracle_key, objective_key, canonical_smiles)` unique; `score`, `wall_ms`, `created_at`. Index on the lookup key.
- Idempotency: an `idempotency_key` unique column on `Run` (or a small `idempotency_keys` table) for retry-safe enqueue.
- All via **Alembic incremental revisions** (the milestone already has a mature 6-revision baseline + adopt-by-stamp path).

## 8. Testing & validation

- **Queue/lease:** unit tests for atomic claim under contention (two workers, one run → exactly one drives; assert no duplicate `Generation.index`); lease-expiry reclaim resumes to the same terminal state (extends the existing replay-determinism tests).
- **Cache:** hit/miss/version-invalidation; canonicalization correctness (distinct SMILES for the same molecule hit the same entry); budget invariant (hit = $0, uncounted in exploratory mode).
- **Backpressure:** intake cap returns `429`/`queued`; bounded pools don't exceed the cap under a burst.
- **Cross-process events:** worker `NOTIFY` → API WS receives within latency budget (integration test against real Postgres, mirroring the existing `aconnect_ws` suite).
- **REST:** pagination cursor stability; idempotent double-`POST` yields one run.
- **Regression gates (must stay green):** backend `ruff` + strict `mypy` + `pytest`; web typecheck/eslint/vitest/axe. The G1 benchmark result and FIGURE CANON are not touched.

## 9. Slice breakdown (high-level — per-slice implementation lives in the build sessions)

Milestone 08 → `docs/08-<name>/`. Vertical slices, ~1 month focused:

1. **Green-on-clone + credibility** (Tier 0 early) — `apps/api` conftest skip-guards, results framing, GIF trim. Independent; ship first. *(S)*
2. **Postgres job queue + out-of-process worker** — lease/heartbeat/`SKIP LOCKED` claim/reclaim; API enqueues; worker drives. *(L — the core)*
3. **Cross-process live events** — `LISTEN/NOTIFY`; WS subscribes; DB snapshot path becomes normal. *(M)*
4. **Persistent shared oracle cache** — table, canonicalization, version invalidation, budget integration. *(M)*
5. **Backpressure + REST gaps** — concurrency caps, bounded pools, pagination, idempotency. *(M)*
6. **Ops** — Dockerfile(s) + compose + `/readyz` + `pool_pre_ping`. *(S–M)*
7. **Reframe & docs** (Tier 0 final) — README lead-with-backend + ELI5, `docs/architecture.md` + "hard problems" narrative. *(S–M)*
8. **(Stretch, uncommitted) Docking on the worker pool** — the expensive workload that justifies the cache. Tier 2 only if 1–7 land early. *(M)*

## 10. Risks & guardrails

- **Cargo-cult perception.** Mitigated by choosing the disciplined option at each fork (Postgres-as-queue over a broker) and *documenting the tradeoff* — the decision trail is itself the "defend your architecture" signal the research rewards.
- **Scope/timeline.** Tier 1 is genuinely ~3–4 weeks; slice 1 + slices 2–3 are the must-haves that deliver the "it's actually distributed now" story. Slices 4–7 are high-value but degrade gracefully if the window tightens. Docking (slice 8) is explicitly cut-first.
- **Benchmark contamination.** All new machinery is orthogonal to the eval path; the G1 result stands; docking (if ever added) is exploratory-mode-only behind the existing `mode.py` wall. N6 holds.
- **Regression.** Branch-first off main; independently re-verify any subagent/Builder claims; full gate-green before each slice ships.

## 11. Alternatives considered

- **Docking-on-Modal as the anchor** (explored first this session) — *rejected as anchor, kept as stretch.* Its systems value (cache + worker pool) is delivered by Tier 1 directly, on the existing cheap oracles, with far less chemistry-integration risk. As an *expensive real workload* on top of the new pool it's a great stretch, not the foundation.
- **Redis / message broker for the queue + events** — *rejected.* At single-user, single-digit-concurrent-runs scale it's prestige infra without fit; the research flags cargo-cult as a negative signal. Postgres `SKIP LOCKED` + `LISTEN/NOTIFY` is sufficient, defensible, and dependency-free. (Revisit only if the workload genuinely outgrows one Postgres.)
- **Tier 0 only (reframe, ship)** — *rejected for this window.* Legible, but leaves the single-process core, so the deepest backend probe still finds thin ice. Worth it only if the runway collapses.
- **Do nothing / keep building product features** — *rejected.* Adds breadth where the research says depth-over-breadth wins, and doesn't touch the acknowledged backend-thinness.
