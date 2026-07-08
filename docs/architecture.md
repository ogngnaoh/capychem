# Architecture

CapyChem's product-facing story is a closed-loop molecular optimization agent. This document is the
systems-facing one: how a run actually moves through the system once `POST /runs` is called — the
durable Postgres queue, the lease/heartbeat/reclaim protocol a worker holds while driving a run, the
cross-process live-event fan-out, the persistent oracle-score cache, cost-gate enforcement, and — the
part worth reading closely — the hard problems this design ran into and how they were actually solved,
including the two known limitations that were deliberately left open rather than papered over.

Everything below describes the shipped system as of milestone `08-backend-systems-depth` (branch
`m08-backend-systems-depth`). No Redis, no message broker, no Celery, no Kubernetes — Postgres is both
the run store and the queue, by design (see §7.1).

**Scope note (N6):** every "score" anywhere in this system is an in-silico PMO/TDC benchmark-oracle
score. Nothing here does or claims real-world drug-discovery efficacy, wet-lab work, or docking — the
architecture is a job-processing/optimization engine that happens to be demonstrated on molecular
scoring. Docking is a documented, uncommitted stretch (milestone 08 slice 08); it is not implemented and
nothing below should be read as claiming it is.

---

## 1. The run lifecycle

A run is a **row in Postgres, not a task pinned to a process**. Any worker process that can see the
database can claim, drive, or resume it.

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI (routes_runs.py)
    participant PG as Postgres (runs / generations / candidates / oracle_calls / run_costs)
    participant Worker as RunRegistry (apps/runner, or the API's inline dev worker)
    participant LLM as DeepSeek-v4-pro
    participant Oracle as PMO harness (subprocess bridge)
    participant Bus as RunEventBus (LISTEN/NOTIFY)
    participant WS as /ws/runs/{id}

    Client->>API: POST /runs {task, budget, ...}
    API->>PG: INSERT runs (status="queued")
    API-->>Client: {run_id, status: "queued"}

    Worker->>PG: SELECT ... FOR UPDATE SKIP LOCKED (claim_next_run)
    PG-->>Worker: run_id (status -> "running", lease_owner/lease_expires_at/heartbeat_at set)

    loop each generation
        Worker->>LLM: propose (+ analyze, after gen 0)
        Worker->>Oracle: score (subprocess + JSON; cache-checked first, see §5)
        Worker->>PG: INSERT generation + candidates + oracle_calls, UPSERT run_costs (commit)
        Worker->>PG: SELECT pg_notify('run_events', pointer) — AFTER the commit above
        PG-->>Bus: NOTIFY run_events
        Bus-->>WS: pointer {run_id, kind, index}  (no event body — see §4)
        WS->>PG: re-read the real event (reconstruct_state / hypothesis query)
        WS-->>Client: generation.complete / analyzer.hypothesis
        Worker->>PG: renew_lease (heartbeat, every lease_ttl/3)
    end

    Worker->>PG: finalize_run (terminal status + summary + manifest), fenced to lease_owner
    Worker->>PG: pg_notify('run_events', {kind: "run.complete"})
    Bus-->>WS: pointer {kind: "run.complete"}
    WS-->>Client: run.complete, then close
```

Code path, in order:

1. `POST /runs` (`apps/api/capychem/api/routes_runs.py::create_run_endpoint`) validates the request,
   derives `mode` (`benchmark` | `exploratory`, `capychem.mode.derive_mode` — never client-set), and
   inserts a `Run` row with `status="queued"` via `capychem.run.create_run`. **The request handler never
   drives the loop itself** — it only enqueues. If an `Idempotency-Key` header is present, a retried
   POST with the same key returns the existing row instead of minting a second run (a pre-check for an
   existing row, plus a race-loser fallback onto the column's `UNIQUE` constraint if two requests race
   past the pre-check together — `routes_runs.py::create_run_endpoint`).
2. A worker — the standalone `apps/runner` process (`capychem_runner.run_forever`), or the API's own
   inline dev/test worker (`CAPYCHEM_INLINE_WORKER=1`, the default outside the Docker Compose
   deployment) — polls the durable queue (`RunRegistry.run_worker_loop`,
   `apps/api/capychem/api/runner.py`) and claims a row via `capychem.db.queue.claim_next_run` (§3).
3. The claiming worker drives the **existing, unmodified LangGraph loop**
   (`capychem.loop.graph.build_graph`: propose → validate → fallback → score → persist → analyze →
   stop_check) via `RunRegistry._drive`, wrapped by `_drive_with_lease` which owns the lease
   renew/release lifecycle (§3). A run with existing `Generation` rows (a crash-reclaim, or a manual
   `/resume`) replays its progress through `capychem.resume.reconstruct_state` before driving — the
   *same* replay path a manual resume uses, so a reclaimed run reaches the same terminal state an
   uninterrupted one would.
4. Each generation's `score`/`_persist` nodes commit `Generation` + `Candidate` + `OracleCall` rows and
   upsert `RunCost` (`capychem.cost.record_oracle_cost`, §6) inside the *same* worker process, using the
   existing async session. Only **after** that commit does the worker call
   `capychem.api.events.notify_run_event` to `pg_notify` a pointer (§4) — notify-after-commit is the
   invariant that makes the DB always the source of truth a receiver can trust.
5. `finalize_run` (`capychem.run.finalize_run`) writes the terminal status, `summary_json`, and the
   reproducibility manifest, **fenced to the current lease owner** (§3.4) so a worker that has since lost
   its lease can never clobber a legitimate reclaiming owner's terminal row. A final `run.complete`
   notify follows unconditionally (even from a fenced-off write — see §3.4).
6. The lease is released (`capychem.db.queue.release_run`) only after a terminal write — never on a
   cancelled/interrupted drive, so an interrupted run's lease is left to expire naturally and is picked
   up by the ordinary reclaim path (no separate boot-time sweep is needed; see §3.3).

---

## 2. WebSocket event schema

`/ws/runs/{run_id}` (`apps/api/capychem/api/ws_runs.py`) streams three event types (Pydantic models in
`apps/api/capychem/api/schemas.py`), each tagged with a `type` discriminator, plus an untagged heartbeat:

```jsonc
// generation.complete — emitted once per completed generation
{
  "type": "generation.complete",
  "generation_index": 3,
  "best_score": 0.91,
  "top10_mean": 0.83,
  "oracle_calls_used": 240,
  "cost_so_far_usd": 1.42,
  "top_k": [{"smiles": "...", "score": 0.91, "quality": {"...": "..."}}]
}

// analyzer.hypothesis — emitted after every generation >= 1
{
  "type": "analyzer.hypothesis",
  "after_generation_index": 3,
  "text": "focus: introduce a hydrogen-bond donor; avoid: halogen substituents",
  "structured_json": {"focus": "...", "avoid": ["..."]}
}

// run.complete — emitted exactly once, terminal
{"type": "run.complete", "run_id": 42, "status": "exhausted", "summary": {"...": "..."}}

// heartbeat — every 15s of silence, keeps the socket warm through cold starts
{"type": "ping"}
```

**Two delivery paths, chosen per-connection by whether *this* API process is driving the run**
(`reg.is_live(run_id)`):

- **Local** — the API process holds the run's in-memory `RunHandle`; the WS subscribes directly to its
  `asyncio.Queue` and forwards events as `RunRegistry._drive` broadcasts them. This is the original,
  single-process path and is unchanged by this milestone.
- **Cross-process** (the new, and now *normal*, path once a separate `apps/runner` process can own the
  drive) — the WS subscribes to `RunEventBus` (§4) *before* reading anything from Postgres (so a
  notify landing in the gap between "check status" and "start listening" is queued, not lost), replays a
  DB snapshot (`_current_generation_event`, built via the same `reconstruct_state` resume uses) to catch
  a late/reconnecting client up, then forwards each subsequent `LISTEN/NOTIFY` pointer as a freshly
  re-read event. A run already terminal at connect time is served its stored terminal event and closed
  immediately.

The NOTIFY payload itself is **not** one of the event bodies above — see §4 for why it's a bare pointer
(`{run_id, kind, index}`) that the receiver resolves back into the real event by re-reading Postgres.

---

## 3. The durable queue: claim, lease, heartbeat, reclaim, fence

`packages/core/capychem/db/queue.py` implements the whole protocol over the `runs` table — no separate
queue table, no broker.

### 3.1 Claim

```sql
SELECT id FROM runs
WHERE status = 'queued'
   OR (status = 'running' AND lease_expires_at < now())
ORDER BY started_at
LIMIT 1
FOR UPDATE SKIP LOCKED
```

`claim_next_run` runs this, then sets `status="running"`, `lease_owner`, `lease_expires_at`, and
`heartbeat_at` in the same transaction. `FOR UPDATE SKIP LOCKED` is the whole trick: a concurrent
claimer racing the same candidate row never blocks on it and never double-claims it — it skips straight
to the next claimable row, or returns `None`. A "running" row whose lease has expired is claimable by
construction (its worker presumably crashed); a queued row and an abandoned running row are the *same*
claim query, oldest-first so nothing starves.

Every comparison uses the **database's** clock (`func.now()`), never a worker's wall clock — skew
between a worker host and Postgres can never cause a premature or missed reclaim.

### 3.2 Lease + heartbeat

A claimed run's lease defaults to 60 s (`CAPYCHEM_LEASE_TTL_S`); `RunRegistry._renew_lease_loop` renews
it (extends `lease_expires_at`, bumps `heartbeat_at`) every TTL/3 — two missed heartbeats of slack before
another worker can reclaim a still-live run. `renew_lease` is **scoped to `lease_owner == worker_id`**:
if another worker has already reclaimed the row, the UPDATE matches zero rows and is a harmless no-op —
a stalled worker's own renewal can never resurrect a lease it no longer owns (§3.4 covers what it does
instead: stop).

### 3.3 Reclaim (crash-safe)

If a worker dies outright, its task is gone but its row's lease keeps counting down; once
`lease_expires_at < now()`, `claim_next_run`'s `OR` clause picks it right back up — no boot-time sweep,
no separate reaper process. The reclaiming worker sees existing `Generation` rows, replays them through
`reconstruct_state`, and resumes from the next generation index. This is exercised directly by
`apps/api/tests/test_worker_queue.py`'s crash-reclaim test (cancel the original task, then reclaim and
verify the run reaches the same terminal state).

### 3.4 Fencing against a *revived*, not dead, worker (m08-02b)

True process death is the easy case — §3.3 covers it cleanly. The gap milestone 08 slice 02b closed is a
**stalled-not-dead worker**: one whose event loop merely hung past its lease TTL (a GC pause, a blocked
call, a slow host), got reclaimed by a second worker, and then *resumed running* — its task was never
cancelled, so without extra guards it could still write into a run it no longer owns. Two structural
fences close this (commit `a3f253d`; behavioral proof in
`apps/api/tests/test_lease_fencing.py::test_zombie_double_write_rejected_and_finalize_does_not_clobber`):

- **`UNIQUE(run_id, index)` on `generations`.** A revived worker's attempt to persist a generation index
  the new owner already wrote raises `IntegrityError` at the database level — not a race that depends on
  either worker's timing being "careful," a structural guarantee.
- **Owner-fenced terminal writes.** `finalize_run` and `release_run` accept an `owner_worker_id` and
  scope their `UPDATE` to `WHERE lease_owner = :owner_worker_id`. A revived worker's finalize/release
  attempt, run under its own (stale) `worker_id`, matches zero rows against a row some other worker now
  owns — a fenced no-op, never a clobber.
- **Stop-on-lost-lease (defense in depth).** `renew_lease` returns whether its `UPDATE` matched a row;
  `_renew_lease_loop` treats `False` as proof another worker now owns this run and sets the drive's
  cooperative-stop signal, so the revived worker stops driving at its next generation boundary instead
  of continuing to burn LLM/oracle calls on a run it can no longer legitimately finish.

**Known, accepted residual (documented honestly, not swept under the rug).** The structural fences above
guarantee no *data corruption* — no duplicate generation, no clobbered terminal row — but they do not
guarantee the *legitimate* reclaiming owner always wins cleanly. In the pathological window where a
revived zombie's generation-N write and the new owner's generation-N write race each other, whichever
commits first wins the `UNIQUE(run_id, index)` slot; if the zombie wins that single race, the *new
owner's* subsequent write to the same index is the one that raises `IntegrityError`, and that owner's
drive falls into its generic error handler and finalizes as a spurious `errored` status — even though it
was the run's rightful driver. This is retryable (a fresh `/resume` picks the run back up from whatever
was actually persisted) and never produces incorrect data — every persisted row is a real, validly scored
candidate from *some* honest generation attempt. Fully closing this would require invasive write-fencing
inside the core LangGraph loop itself (every node write, not just the queue boundary, checking current
lease ownership before committing) — real regression risk to the loop that both `benchmark` runs and the
committed G1 result depend on, for a race window that only opens when a worker is stalled long enough to
lose its lease and then *keeps running*. Deliberately not built at this scale; recorded here rather than
silently accepted.

### 3.5 Backpressure

`RunRegistry.claim_and_drive_once` checks `MAX_CONCURRENT_RUNS` (default 4, `CAPYCHEM_MAX_CONCURRENT_RUNS`)
**before** touching the database: a worker already at capacity never claims a row it isn't about to
drive, so the row stays `queued` for this worker's next free slot or for another worker/replica. `POST
/runs` always returns `"queued"` regardless of capacity — the cap is invisible to the producer, which is
why a 429 was rejected in favor of this (the queue already models "not started yet" durably; there is no
reason to make the caller retry).

---

## 4. Cross-process live events: Postgres LISTEN/NOTIFY

Once a run can be driven by a *different* process than the one serving a WebSocket client, that API
process may hold no in-memory state for the run at all — its old single-process `broadcast()` has nobody
local to reach. `RunEventBus` (`apps/api/capychem/api/events.py`) is the cross-process transport:

- **One shared channel (`run_events`), not one per run.** A per-run channel would need the listening
  connection to dynamically `LISTEN`/`UNLISTEN` as WS clients (dis)connect, with a ref-count so one
  client's `UNLISTEN` doesn't strand another. The shared channel instead holds **one dedicated `asyncpg`
  connection per process, for the process's whole lifetime** (SQLAlchemy's pooled async engine has no
  clean persistent-notification API, so this bypasses it entirely), and fans every notification out to
  the right local `run_id` subscribers via an in-process dict. Every API process receives every run's
  traffic system-wide; at CapyChem's single-digit-concurrent-runs scale that's a JSON-decode + dict
  lookup per generation, not a real cost.
- **The payload is a pointer, never the event body.** A Postgres `NOTIFY` payload is capped around 8000
  bytes, and a `generation.complete` event's `top_k` (up to 10 molecules, each carrying a quality report)
  can approach that. The payload is instead `{run_id, kind, index}`; the receiver re-reads the real event
  from Postgres — already the authoritative source for the DB-snapshot/replay path — keyed by that
  pointer.
- **Notify-after-commit, always.** Every call site (`apps/api/capychem/api/runner.py::_notify_best_effort`)
  fires `pg_notify` only after the write it announces has already committed, so a receiver that re-reads
  the instant it gets the notification never sees a stale row.
- **Best-effort by design.** A dropped notification is not a correctness bug: the WS's DB-snapshot
  catch-up on connect/reconnect (§2) recovers from any gap, so a notify failure never aborts a drive
  (`_notify_best_effort` swallows and logs). This also means `pg_notify` — which doesn't exist on SQLite
  — safely no-ops for the fast SQLite-backed direct-runner unit tests instead of erroring them.

---

## 5. The persistent oracle-score cache

`OracleScoreCache` (`packages/core/capychem/db/models.py`) plus `packages/core/capychem/cache.py`
implement a cross-run, cross-process cache keyed on
`(oracle_key, objective_key, canonical_smiles) -> (score, wall_ms)`:

- **`oracle_key`** folds in the harness's *live* PyTDC pin (`capychem.oracle.pytdc_version`, itself a
  cheap analytic probe of the running harness). Bumping the harness's pinned oracle version changes the
  key for free — every stale entry simply stops matching, with no migration or backfill needed.
- **`objective_key`** is the plain PMO task name for a benchmark task, or a stable SHA-256 hash of a
  composed objective spec (`capychem.objective.stable_hash`, key order normalized via `sort_keys=True`)
  for a custom exploratory objective — two objectives that are semantically identical but built in a
  different field order still share one cache entry.
- **Canonicalization** goes through RDKit (`capychem.validate.canonicalize`) on every lookup and write,
  so two distinct SMILES strings for the same molecule (different atom ordering, different but equivalent
  ring-closure numbering, etc.) resolve to the same cache row.
- **A hit is free.** `_cache_lookup` (`packages/core/capychem/loop/graph.py`) is consulted *before* the
  real oracle call; a hit costs `$0` and never touches `mol_buffer`/`calls_used` — it doesn't spend the
  run's oracle-call budget.
- **Race-tolerant writes.** `record_many` writes newly-computed scores back best-effort: a duplicate-key
  race (two runs discovering the same new molecule at nearly the same instant) is resolved first-writer-
  wins, with the loser's `IntegrityError` swallowed row by row so the rest of the batch still lands.

**The benchmark/exploratory wall (the one invariant this cache must never cross).** The cache is
**exploratory-mode-only** — `_cache_lookup`/`_cache_write` no-op immediately whenever `mode != "exploratory"`
or no sessionmaker is supplied. The benchmark scoring branch in the `score` node is untouched, byte-
identical code whether this table exists or not, and the eval/benchmark harness
(`packages/core/capychem/eval/runner.py`) is a **fully separate code path** that never calls
`build_graph`/`score_batch_async` at all — it uses its own `mol_buffer` dict and a synchronous
`score_smiles` call. Neither the live benchmark-mode API path nor the eval harness can ever read from or
write to this cache. The committed G1 result
(`docs/04-compare-and-polish/g1-full23-10k-seed42.json`) is produced entirely outside this code and is
untouched by this milestone. This is proven directly by
`packages/core/tests/test_oracle_score_cache.py::test_benchmark_mode_never_touches_cache`.

**Known, accepted limitation (operator-approved deferral): exploratory cache hits over-count on resume.**
A live exploratory run treats a cache hit as free and uncounted against `calls_used`/the oracle budget
(above). But a cache-hit candidate is still **persisted** as an ordinary `Candidate` + `OracleCall` row
(`_persist` in `loop/graph.py` writes every entry in `_scored`, cache hits included, with
`compute_cost_usd=0.0`) — there is currently no column distinguishing "this candidate's score came from
a cache hit" from "this candidate was freshly scored." `reconstruct_state`
(`packages/core/capychem/resume.py`), which rebuilds a resumed run's `mol_buffer`/`calls_used` by
replaying *every* persisted candidate per generation, therefore has no way to exclude those free hits —
it re-counts them as spent budget. Net effect: **a resumed exploratory run that had cache hits before it
was interrupted can end up with a slightly higher `calls_used` (and a correspondingly shifted AUC curve)
than the same run would have shown had it never been interrupted.** This is:

- **Non-corrupting** — every persisted molecule and score is real; nothing is fabricated or lost.
- **Exploratory-only** — the benchmark scoring path never reaches this code at all (see the wall above),
  so the committed G1 result and every benchmark-mode run are completely unaffected.
- **Narrow** — it only manifests for a run that is (a) exploratory, (b) had at least one cache hit, and
  (c) was interrupted and resumed.

A proper fix needs a way to distinguish cache-hit candidates from freshly-scored ones through persistence
and back out through `reconstruct_state` (e.g. a `from_cache: bool` column, or a distinct
`OracleCall.compute_cost_usd == 0.0 AND cache hit` marker plumbed through resume's replay). The operator
reviewed this at the milestone's S6 gate and chose to document it here and defer the fix rather than gate
the milestone on it — recorded as a deferred follow-up in `docs/08-backend-systems-depth/log.md`.

---

## 6. Cost-gate enforcement

`RunCost.total_usd = oracle_cost_usd + llm_cost_usd` (`packages/core/capychem/cost.py`), unconditionally
— missing either half would let the ~$50/run gate silently fail to fire. Every generation, after that
generation's `Candidate`/`OracleCall` rows commit, the worker (`RunRegistry._drive`) sums
`oracle_cost_so_far` from persisted `OracleCall.compute_cost_usd` and adds the loop state's cumulative
`llm_cost_usd`, upserts the run's single `RunCost` row via `record_oracle_cost`, and compares the new
total against `cost.cost_cap_usd()` (default `50.0`, overridable via `CAPYCHEM_COST_CAP_USD`). Once the
total meets or exceeds the cap, the drive breaks cleanly **after** that generation's state is already
durable, and the run finalizes with terminal status `cost_capped` — a reactive absolute cap, evaluated
once per completed generation, never a mid-generation abort and never a projection.

---

## 7. Hard problems + tradeoffs I solved

### 7.1 Postgres-as-queue vs. a broker (Redis/Kafka/RabbitMQ/Celery)

**Decision: Postgres `SKIP LOCKED`, no broker.** At CapyChem's actual scale (single-digit concurrent
runs, ~30 generations/run, a human operator launching runs from a web UI) a broker adds an entire second
stateful system to operate, back up, and reason about failure modes for, in exchange for throughput this
project will never need. Postgres was already the run store; `SELECT ... FOR UPDATE SKIP LOCKED` gives
exactly the claim semantics a broker would (exactly-one-claimer, non-blocking skip-on-contention) without
a second source of truth to keep consistent with the first. The real cost of this choice is throughput
ceiling (a broker scales claim throughput far past what a single Postgres table can) and the absence of
built-in dead-letter/retry tooling a mature broker ships — both irrelevant at this project's scale, and
both would become real arguments the moment concurrent-run counts grow by orders of magnitude. Choosing
the disciplined, smaller-surface option here — and writing down *why*, including where it would stop
being the right call — is the point of this section, not an oversight.

### 7.2 Cross-process live events without a pub/sub broker

The naive alternative to `LISTEN/NOTIFY` here is polling: every API process periodically re-queries "did
anything change for a run I have subscribers on." That trades an idle connection (the LISTEN/NOTIFY
approach's real cost: one dedicated `asyncpg` connection held open per process for its whole lifetime)
for either wasted query load (poll too often) or added latency (poll too rarely) — and CapyChem's G5
requirement is sub-2-second p95 live-update latency, which a coarse poll interval fights directly.
`LISTEN/NOTIFY` gives push semantics essentially for free once you're already on Postgres, at the cost of
SQLAlchemy's async engine not exposing it cleanly (solved by holding a raw `asyncpg` connection
independent of the app's pooled engine — see §4) and the 8000-byte payload ceiling (solved by sending a
pointer, never the body — also §4).

### 7.3 Cache canonicalization and invalidation

Two molecules that are chemically identical can be written as different SMILES strings (different atom
traversal order, different but equivalent ring-closure numbering). Caching on the raw string would silently
under-hit — the exact bug a cache exists to avoid. Running every key through RDKit's canonical SMILES
(`Chem.MolToSmiles(Chem.MolFromSmiles(s))`) collapses that variance to one representation before either a
lookup or a write. Invalidation is solved by *not* needing an invalidation mechanism at all: folding the
harness's live oracle version into the cache key (`oracle_key`) means a version bump changes the key
outright — stale rows simply stop matching, ever, with zero migration or backfill logic to write, test, or
get wrong.

### 7.4 Crash-safe lease reclaim, and its harder cousin (fencing)

The easy 80%: a dead worker's task is gone, its lease keeps ticking down, another worker reclaims once it
expires (§3.3) — cleanly testable by literally cancelling a task and asserting reclaim. The harder 20%,
and the part worth calling out explicitly, is that "the worker is dead" is an assumption, not a
guarantee: a worker whose event loop merely *stalled* past the lease TTL is not dead, and if it resumes
after being reclaimed it will keep trying to act as if it still owns the run. Solving this required
moving from "trust the lease" to "verify ownership at every write that matters" — the `UNIQUE(run_id,
index)` structural backstop and the owner-scoped `finalize_run`/`release_run` writes in §3.4 — and
explicitly deciding *not* to chase the residual race all the way down into the core loop's own write path,
because that tradeoff (real regression risk to the loop every benchmark run and the committed G1 result
depends on, against a vanishingly narrow race window) wasn't worth it at this scale. That decision, and
the residual it leaves open, is documented in §3.4 rather than hidden.

### 7.5 The exploratory-cache / resume interaction

Documented in full in §5's "known, accepted limitation." Worth stating plainly here too: this is the
kind of bug that is easy to miss because each half is independently correct — the live cache-hit-is-free
logic is correct, and `reconstruct_state`'s "replay every persisted candidate" logic is correct for the
world before the cache existed — and the interaction only surfaces once both exist and a run happens to
be interrupted mid-flight with a cache hit already banked. Caught during this milestone's own gate review
(not by a user report), and consciously deferred rather than rushed, because a real fix touches the
persist/replay contract shared by every run in the system and deserves its own focused slice rather than
a same-day patch riding in under a docs slice.

---

## 8. What this is not

No Redis, no message broker, no Celery, no Kubernetes anywhere in this system — the queue is Postgres
`SKIP LOCKED`; the event bus is Postgres `LISTEN/NOTIFY`. No docking, no AutoDock Vina/DiffDock worker
pool, no expensive-oracle integration — those remain a documented, uncommitted stretch (milestone 08
slice 08) and are not implemented. No claim of real-world drug-discovery efficacy anywhere in this
document or the system it describes (N6): every score this architecture schedules, caches, and serves is
an in-silico PMO/TDC benchmark-oracle score.
