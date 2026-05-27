# SPEC: CapyChem

**Status:** Draft
**Last updated:** 2026-05-26
**Related PRD:** ./PRD.md
**Related context bundle:** ./PROJECT.md

## 1. TL;DR

CapyChem is an autonomous closed-loop molecular optimization agent: design → score → analyze → redesign over a fixed oracle-call budget. The implementation is a Next.js web app talking to a FastAPI backend that runs a LangGraph-orchestrated loop; the proposer/analyzer LLM (DeepSeek-v4-pro) and the oracle worker pool both run on Modal; run state lives in managed Postgres; every loop step is traced to a self-hosted Langfuse. The headline narrative is **agentic depth + rigorous evaluation against published PMO baselines**, with backend (Modal serving, async batching, WebSocket live updates) doing real but supporting work. The single biggest trade-off: the legacy PMO eval harness pins old dependencies (PyTDC 0.3.6 / Python 3.10) and must live in an isolated environment that modern code calls via subprocess, not import.

## 2. Context

Greenfield 16-week build by a solo developer with strong SWE skills, multi-framework agentic experience, and no chemistry background. The framing audience is drug-discovery scientists (the PRD persona); the substantive audience is BigTech SWE+AI/ML internship recruiters reading the GitHub repo and writeup. The PRD's user stories are honest for the framing audience; the engineering decisions below optimize for both: defensible chemistry-domain story AND legible system design without chemistry knowledge.

The reference architecture is MOLLEO (LLM-as-mutation operator inside Graph-GA). MOLLEO has no analyze step — that's the gap CapyChem closes and the basis for both the "closed-loop" and "agentic depth" claims. The Week-1 differentiator-confirm task in PROJECT.md §11 reads MOLLEO's source to verify this narrative.

## 3. Goals

Restating PRD goals with implementation-level numeric targets:

- **G1 — Benchmark.** Beat vanilla Graph-GA on ≥6 of 23 PMO tasks by AUC of top-10 mean score under a 10,000-oracle-call budget, by **2026-09-15**.
- **G2 — End-to-end loop.** Full propose → score → analyze → redesign cycle on any PMO task under the 10,000-call budget at <~$50 compute equivalents, by **2026-08-04**.
- **G3 — Web surface.** Launch / watch-live / browse-results / compare across all 23 tasks, by **2026-09-15**.
- **G4 — Loop reliability.** ≥99% loop-step success (validation + retry + fallback path) across a complete 10,000-call run.
- **G5 — Live-update latency.** WebSocket broadcast of a generation event to the client at <2 s p95.
- **G6 — Eval reproducibility.** Same task + same seed + same proposer model yields identical AUC top-10 ±1% across runs.

## 4. Non-goals

PRD non-goals N1–N6 carry forward. Engineering-level additions:

- **N7** No Kubernetes. Modal is the orchestration substrate; we don't run a k8s cluster.
- **N8** No multi-tenant infrastructure. Single-user demo posture (PRD covers this).
- **N9** No novel ML training. Off-the-shelf LLMs only; no fine-tuning, no LoRA.
- **N10** No production observability stack beyond Langfuse + structured logs. No Datadog/Prometheus/Grafana in MVP.
- **N11** No mobile or native clients. Web only.

## 5. Technical context

| Layer | Choice | Version |
|---|---|---|
| Frontend | Next.js (App Router) + React + TypeScript + Tailwind + shadcn/ui | Next 15, React 19, TS 5.x |
| Backend API | FastAPI | 0.115+ |
| Agent orchestration | LangGraph | current at impl time |
| Observability | Langfuse, self-hosted via Docker Compose | current OSS image |
| Proposer + Analyzer LLM | DeepSeek-v4-pro via Modal-served inference | model weights pinned by digest |
| Eval harness | `mol_opt` (PMO, MIT) + PyTDC | PyTDC 0.3.6, Python 3.10 (legacy, isolated) |
| Cheminformatics | RDKit | current |
| Compute | Modal | LLM endpoint + oracle worker pool |
| Data store | Managed Postgres (Neon or Supabase — picker at infra-setup) | Postgres 16 |
| Python tooling | uv + ruff + pytest + mypy | mypy strict on new code |
| Monorepo tooling | pnpm workspaces (Node) + uv workspaces (Python) | Node 22 LTS, Python 3.12 |

Performance / scale: single concurrent user; single-digit concurrent runs in MVP; per-run state up to ~10,000 candidates and ~30 generations. The 10,000-oracle-call budget bounds the per-run workload.

## 6. Proposed design

### 6.1 Architecture overview

```
  ┌────────────────────────┐
  │  Next.js web (App      │
  │  Router, TS, shadcn)   │ ── REST + WebSocket ──┐
  └────────────────────────┘                       │
                                                   ▼
                                       ┌───────────────────────┐
                                       │  FastAPI              │
                                       │  - REST /runs/*       │
                                       │  - WS /ws/runs/{id}   │
                                       │  - LangGraph runtime  │
                                       └──────────┬────────────┘
                                                  │
        ┌──────────────────┬──────────────────────┼──────────────────┐
        ▼                  ▼                      ▼                  ▼
  ┌──────────┐    ┌──────────────┐      ┌──────────────────┐   ┌────────────┐
  │ Postgres │    │ Modal LLM    │      │ Modal oracle     │   │  Langfuse  │
  │ (run     │    │ endpoint     │      │ worker pool      │   │  (self-    │
  │  state)  │    │ (DeepSeek    │      │ (PMO/PyTDC, RDKit│   │  hosted)   │
  └──────────┘    │  v4-pro)     │      │  via subprocess  │   └────────────┘
                  └──────────────┘      │  to harness env) │
                                        └──────────────────┘
```

`apps/web` is the only client. `apps/api` owns REST + WS and hosts the LangGraph runtime in-process; long-running loops run as background tasks within the API process, persisting state to Postgres after each generation. `apps/worker` is a Modal app exposing two endpoints: `llm.propose(batch, prompt)` and `oracle.score(smiles_batch, task)`. The oracle worker shells out to the **pinned `harness/` conda env** via subprocess + JSON; this is the only bridge between the modern stack and the legacy `mol_opt` + PyTDC environment.

### 6.2 Data model

Entities (Postgres):

- **Run** — `id`, `task` (PMO task name), `budget`, `mutation_strategy`, `plateau_window`, `status` (queued|running|plateaued|exhausted|stopped|errored), `started_at`, `ended_at`, `seed`, `config_json` (full launch config), `summary_json` (top-K + AUC at end).
- **Generation** — `id`, `run_id`, `index`, `started_at`, `ended_at`, `proposer_used` (model|fallback|mixed), `analyzer_hypothesis_id` (nullable on gen 0), `events_json` (Langfuse trace IDs).
- **Candidate** — `id`, `generation_id`, `smiles`, `selfies` (nullable), `parent_candidate_id` (nullable), `proposer` (model|fallback), `valid` (RDKit), `score` (nullable until scored), `oracle_call_id` (nullable).
- **OracleCall** — `id`, `run_id`, `candidate_id`, `task`, `score`, `wall_ms`, `compute_cost_usd`.
- **AnalyzerHypothesis** — `id`, `run_id`, `after_generation_index`, `text`, `structured_json` (parsed hypothesis if extractable), `tokens_in`, `tokens_out`, `compute_cost_usd`.
- **RunCost** — `id`, `run_id`, `llm_cost_usd`, `oracle_cost_usd`, `total_usd`. Updated at run completion; live-estimated during run via summing OracleCall + AnalyzerHypothesis + per-generation proposer cost.

Retention: indefinite for MVP (single-user, low volume). Indexes: `(run_id, generation_index)`, `(run_id, score DESC)`, `(task, status, started_at DESC)`.

### 6.3 Interfaces

**REST (FastAPI):**

- `POST /runs` — body: `{task, budget, mutation_strategy, plateau_window, seed?}` → `{run_id, status}`.
- `GET /runs` — query: `status?, task?, sort?, limit?, cursor?` → `[{run_id, task, status, best_score, oracle_calls, started_at}]`.
- `GET /runs/{id}` — full run detail with top-K, AUC series, hypotheses, cost.
- `POST /runs/{id}/stop` — terminate cleanly; partial state persisted.
- `GET /compare?a={id}&b={id}` — side-by-side comparison payload.
- `GET /trace/{run_id}` — Langfuse deep link.
- `GET /healthz` — liveness.

**WebSocket:** `/ws/runs/{id}` — server pushes events as the loop emits them:
- `generation.started` `{generation_index}`
- `candidate.proposed` `{generation_index, candidate_id, smiles, proposer}` (batched)
- `oracle.scored` `{candidate_id, score}` (batched)
- `analyzer.hypothesis` `{after_generation_index, text, structured_json}`
- `generation.complete` `{generation_index, best_score, oracle_calls_used, cost_so_far_usd}`
- `run.complete` `{run_id, status, summary}`

Client subscribes on opening a run-detail or live view; server replays the last N events on connect so reload doesn't lose context.

**Modal worker endpoints:**
- `llm.propose(batch_size, prompt, run_id) -> [{smiles, raw}, ...]` — invokes DeepSeek-v4-pro.
- `llm.analyze(generation_summary, run_id) -> {text, structured_json}` — invokes DeepSeek-v4-pro with analyzer prompt.
- `oracle.score(smiles_list, task) -> [{score, wall_ms}, ...]` — invokes the harness env via subprocess.

### 6.4 Key flows

**(a) Launch a run.** Client `POST /runs` → API validates inputs (FR-001, FR-015) → inserts `Run(queued)` → schedules a LangGraph task in-process → returns `run_id`. Client routes to live view, opens WS `/ws/runs/{id}`. LangGraph runtime advances to `generation 0`: seed population from PMO defaults or operator input. For each generation: call `llm.propose` → validate each SMILES with RDKit → for any invalid output, **trigger the Graph-GA fallback operator on the parent population** (FR-005) → call `oracle.score` → persist Candidates + OracleCalls + budget update → if not at gen 0 emit AnalyzerHypothesis via `llm.analyze` → emit `generation.complete` → repeat. Loop terminates on budget exhaustion (FR-002), plateau (FR-003), or operator stop.

**(b) Analyze step (the differentiator).** After every generation ≥1, the analyzer receives a compact JSON summary: top-k candidates with scores, bottom-k with scores, recent score deltas, the prior hypothesis (if any). It returns prose + a structured JSON hypothesis (e.g., `{"focus": "increase logP", "avoid": ["phenol groups"]}`). The next generation's proposer prompt is templated with the hypothesis text and the structured fields. The hypothesis is persisted to Postgres and emitted over WS. If the analyzer output fails structural parsing, the system uses the prior good hypothesis with a "no new signal" note (FR-007, edge case 3).

**(c) Graph-GA invalid-fallback.** When `llm.propose` returns an invalid SMILES, the system attempts up to *N* retries on that batch slot; if still invalid, the slot is filled by a deterministic graph-edit mutation on a parent from the current top-K. This guarantees full-throughput generations even if the LLM degrades (FR-005, NFR reliability, kill-switch §9 of PROJECT.md).

**(d) Compare runs.** `GET /compare?a={id}&b={id}` returns both runs' top-K, AUC time series (resampled to a common x-axis of oracle calls), hypothesis sequences, and cost. The web view overlays the AUC curves and presents top-K side by side.

## 7. Alternatives considered

The genuine load-bearing section of this SPEC.

### Alt A — MOLLEO-faithful clone (no analyze step)
**Decision:** rejected.
LLM-as-mutation inside Graph-GA, no analyze loop. Cheaper to build, fewer moving parts, no hypothesis-management code. But it strips the differentiator: a MOLLEO clone is not a portfolio piece — the closest reference architecture is already public and read-only (PROJECT.md §5). Without the analyze step, the "closed loop" and "agentic depth" claims both collapse.

### Alt B — One-shot tool-use agent (ChemCrow-style)
**Decision:** rejected.
A single agent reasons over the whole optimization in one go, invoking the oracle as a tool. Smaller surface, less infrastructure. But the sequential-decision story disappears, sample-efficiency benchmarking becomes apples-to-oranges with PMO (designed for iterative methods), and the resulting work reads as "agent does the thing" rather than "agent runs a closed loop." Misaligned with the locked PRD anchor.

### Alt C — Multi-agent planner/executor/critic
**Decision:** rejected to MVP; revisit as stretch.
Three specialist agents (planner, executor, critic) coordinated by a router. Strongest "agentic depth" story. But scope explodes: per-agent prompts, message-passing protocol, additional traces to manage; coordinator failure modes multiply. Inside a 16-week solo build, this fights the eval work that earns G1. Defer; the single-LLM proposer+analyzer split already carries the narrative.

### Alt D — Skip Modal, use a paid LLM API
**Decision:** rejected.
GPT-4o or Claude over the public API would skip the Modal serving infrastructure. Faster to wire; no GPU cold-start surprises. But (1) DeepSeek-v4-pro is the chosen model — Modal-served inference is the realistic path for it; (2) per-token cost at 10,000 oracle calls easily blows past the ~$50/run gate (PROJECT.md §9); (3) loses the backend depth that the web-first surface justifies. The Modal LLM + Modal oracle workers + WebSocket-driven UI together carry real engineering load even though the *narrative* headline is agentic+eval.

### Alt E — SQLite + LiteFS instead of managed Postgres
**Decision:** rejected.
Simpler ops, single-file portability, no managed-service dependency. But the web view reads while a worker writes — concurrent-write awkwardness is real once we have a live run + a browse session at once. Postgres also keeps doors open for `pgvector`-backed memory-of-past-mutations (PROJECT.md §8 stretch). Operational cost of managed Postgres is rounding-error inside the $50/run cost gate.

### "Do nothing" baseline
Keep working on assorted demos. No portfolio anchor, no closed-loop optimization learnings, no answer to "show me one substantial thing you built end to end" in internship interviews. The dual audience (chemist framing + recruiter substance) is the entire point of this project; the do-nothing baseline doesn't serve either.

## 8. Cross-cutting concerns

### 8.1 Security
- **Auth:** none. Single-user demo posture; PRD non-goal coverage is implicit.
- **Secrets:** Modal tokens, Langfuse keys, Postgres DSN, model-registry tokens — all in environment variables, never committed. Local `.env.local` is gitignored; deployed secrets live in Modal's secret store and the host's env.
- **CORS:** locked to `localhost:3000` + the deployment origin. No wildcards.
- **Input handling:** the only operator free-text input is SMILES strings in seed-population overrides. RDKit parses every SMILES before persistence; invalid SMILES are rejected at the API boundary.
- **Subprocess boundary:** the `oracle.score` worker shells out to the legacy `harness/` env with a strictly-typed JSON payload; the worker does not exec arbitrary code from the operator.
- **Blast radius if compromised:** the system has no PII, no third-party user accounts, no production data. Worst-case is leaked Modal/LLM credentials and unauthorized compute spend. Mitigation: env-only secrets, billing alerts on Modal.

### 8.2 Privacy
- **PII:** none collected, ever. PRD non-goals N1 + N3 cover this at the product level.
- **Telemetry:** Langfuse traces capture only the agent's own decisions (prompts, completions, scores). No operator telemetry beyond run-launch inputs.
- **Retention:** indefinite by default for run state (single-user demo); operator can delete runs via API.
- **Deletion:** `DELETE /runs/{id}` cascades to Generations, Candidates, OracleCalls, AnalyzerHypotheses, RunCost. Langfuse traces are deleted via the Langfuse API in the same cascade.

### 8.3 Observability
- **Tracing:** every LangGraph node (`propose`, `validate`, `score`, `analyze`, `redesign`, `stop_check`) emits a Langfuse span. Spans are nested under a per-run trace; per-generation spans nest within. LLM calls capture model, prompt, completion, tokens, latency. Oracle calls capture task, SMILES, score, wall time.
- **Logs:** structured JSON from FastAPI and the Modal workers, keyed by `run_id` and `generation_index`. Stdout only in MVP; aggregation deferred (N10).
- **Metrics:** per-run `llm_cost_usd`, `oracle_cost_usd`, `valid_smiles_rate`, `loop_step_success_rate`, `ws_broadcast_latency_ms_p95` — surfaced on the run-detail view and emitted as Langfuse events.
- **Health:** `/healthz` on `apps/api` and the Modal worker; both check downstream connectivity (Postgres, LLM endpoint) shallowly.
- **Cost-budget enforcement:** the API rejects new generations when `RunCost.total_usd` projects past 1.5× the user's configured budget, surfacing a cost-gate event.

## 9. Rollout & migration

No migration — greenfield. The 16-week build runs in four phases (kill-switch gates from PROJECT.md §9 attached):

- **Phase 1 (weeks 1–3) — harness reproducibility & loop spike.** Stand up the pinned `harness/` conda env (PyTDC 0.3.6, Python 3.10); reproduce one Graph-GA PMO result. Wire LangGraph + Langfuse around a trivial `LLM → TDC oracle → log` loop. Measure valid-SMILES rate. **Kill-switch:** <80% valid SMILES or harness won't reproduce → fix before proceeding.
- **Phase 2 (weeks 4–7) — end-to-end loop on one PMO task with web shell.** Modal LLM endpoint + Modal oracle worker pool; FastAPI REST + WS skeleton; Postgres schema; minimal Next.js launch + watch-live view on one PMO task; first ≥6/23 beat-Graph-GA attempt on a single task. **Kill-switch:** can't reproduce MOLLEO-like beat on a single task by week 7 → narrow scope before scaling.
- **Phase 3 (weeks 8–12) — analyzer agent + full benchmark surface.** Implement the analyzer step (the differentiator); roll out across all 23 PMO tasks; cost gate checks. **Kill-switch (the PROJECT.md §9 Week-8 bar):** beat Graph-GA on ≥3 of 23 tasks → on track; <3 → **pivot to analyzer-only narrative**, not abandon.
- **Phase 4 (weeks 13–16) — compare view + polish + Langfuse-driven writeup.** Compare-runs flow; web app polish; README + Langfuse trace walkthroughs that are recruiter-legible without chemistry knowledge.

Deployment: containerized FastAPI + Postgres + Langfuse via Docker Compose for local dev; Modal handles its own deployment via the `modal deploy` command. The web app deploys statically (Vercel or Cloudflare Pages — picker at deployment time).

## 10. Testing & validation

- **Unit tests (pytest):** `packages/core` — loop step transitions, SMILES validation + fallback path, analyzer-output parsing, plateau detection, budget enforcement.
- **Integration tests (pytest + a Modal sandbox):** `apps/api` against a stub LLM and stub oracle; end-to-end loop on a synthetic 100-call mini-task; WebSocket event sequence.
- **Frontend tests:** Playwright smoke tests on US-1..US-4 (launch / watch-live / browse / compare). Vitest for component logic.
- **Eval suite (the load-bearing test):** `uv run capychem-eval --task=<name> --budget=10000 --seed=<n>` runs a full PMO task and emits an AUC report. CI runs a smoke version (budget=200) per merge; the full 23-task sweep is on-demand (cost-bounded). AUC reports versus committed Graph-GA baselines are diffed; regressions fail CI.
- **Reproducibility check (G6):** same task + same seed + same model snapshot → identical AUC top-10 across runs (tolerance ±1%).
- **Manual verification at each phase gate:** the kill-switch checks in §9 are exercised before the phase advances.

## 11. Risks & open questions

**Risks:**

- **Dependency-surface isolation.** `mol_opt` pins PyTDC 0.3.6 / Python 3.10. Modern code MUST NOT share env. Mitigation: subprocess + JSON bridge; CLAUDE.md gotcha; isolated `harness/` directory. *(PROJECT.md §5 hazard, week-one focus.)*
- **LLM cost overrun.** A 10,000-call run with a costly LLM blows the $50/run gate. Mitigation: per-run cost tracking with hard cap (§8.3 cost-budget enforcement); fallback to a smaller-context prompt or a smaller open model (PROJECT.md §9 cost gate). *(PROJECT.md §9.)*
- **Valid-SMILES rate from chosen LLM.** If DeepSeek-v4-pro's valid-SMILES rate is <80% in early spikes, the loop wastes oracle budget on fallback. Mitigation: Week-1 gate + few-shot prompt engineering + structured output enforcement.
- **Modal cold-start latency in WS UX.** First-token from a cold model can be ~30 s; the WebSocket layer must buffer client events through it without disconnecting. Mitigation: WS heartbeat ping; loading-state UX; warm pool on Modal for active runs.
- **Next.js ↔ FastAPI WebSocket proxying.** App Router has historically had quirks proxying WS through middleware. Mitigation: WS endpoint served from an absolute URL (the FastAPI origin), no proxying through Next.
- **Analyzer reasoning may not actually help.** Per kill-switch, if the analyzer doesn't deliver value, pivot to analyzer-only narrative (PROJECT.md §9 Week-8 fallback) rather than abandon.

**Open questions:**

- Managed-Postgres provider: Neon vs Supabase. Decide at infra-setup time. Trade-off: Neon's branching is convenient for eval reproducibility; Supabase bundles auth + storage we don't need but provides a cleaner dashboard.
- Whether to expose raw per-oracle-call cost in the UI or only per-run rollups. Defer until post-Phase-2 user testing.
- Plateau-window defaults (PRD open question 1): tune during Phase 2 once we have real AUC trajectories.
