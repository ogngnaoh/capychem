# Milestones

> Index of CapyChem milestones in execution order, as a shipped history. Phases referenced below correspond to SPEC §9.

01. 00-walking-skeleton — shipped (2026-06-12)
    Thin end-to-end slice (1 PMO task, no analyzer, minimal UI). Surfaces integration risk before rigor.
02. 01-harness-reproducibility — shipped (2026-06-16)
    SPEC Phase 1. Pinned harness env reproduces a Graph-GA PMO result; trivial LangGraph + Langfuse loop spike; per-run valid-SMILES measurement plumbed (>80% gate check rides with the LLM proposer in milestone 02).
03. 02-end-to-end-loop — shipped (2026-06-28)
    SPEC Phase 2. Modal LLM + worker pool; FastAPI REST + WS; Postgres; launch + watch-live on one PMO task; first beat-Graph-GA attempt.
    Slices: 01 launch-and-watch-jnk3 ✓ · 03 modal-llm-propose ✓ · 04 llm-proposer+ga-fallback ✓ · 05 unique-call-budget+cost-ledger ✓ · 06 beat-graph-ga finale ✓ (LLM beats GA on jnk3, week-7 kill-switch passed) · 02 plateau-stop ✓ (FR-003 plateau stop + live signal). All slices shipped → milestone complete.
04. 03-analyzer-and-scale — shipped (2026-06-30)
    SPEC Phase 3. Analyzer agent (the differentiator); all 23 PMO tasks; cost gate; Week-8 bar (≥3/23 beat → on track).
    Slices: 01 analyzer-agent ✓ · 02 analyzer-value-verdict ✓ · 06 analyzer-conditioning ✓ (WIN +0.090/+0.108) · 04 twenty-three-task-surface ✓ · 05 week-8-sweep-and-gate ✓ (bar CLEARED, 7 beats) · 03 analyzer-live-surface ✓ (WS+REST+UI hypothesis surface). All slices shipped → milestone complete.
05. 04-compare-and-polish — shipped (2026-07-01)
    SPEC Phase 4. Compare-runs flow; web polish; legible README + Langfuse trace walkthroughs.
    Slices: 01 runs-list-and-browse ✓ · 02 compare-runs ✓ · 03 web-polish ✓ · 04 g1-full-23-sweep ✓ (G1 MET, 21/21 comparable) · 05 readme-and-langfuse-walkthrough ✓ (README + Langfuse walkthrough; folded in trace-link FR-014). All slices shipped → milestone complete.
06. 05-operator-workbench — shipped (2026-07-02)
    UI/UX legibility redesign over the shipped engine: console-with-a-home workbench (Overview · Workbench · Runs · Compare), hybrid intent launcher, cockpit surfacing reasoning + beat-Graph-GA rigor. Agent-team Builder ↔ Critic, four human checkpoints.
    Slices: 01 low-fi-wireframes ✓ (CP1) · 02 hifi-surfaces-and-launcher ✓ (CP2) · 03 productionize-and-wire ✓ (CP3). All slices shipped → milestone complete (2026-07-02). Backend (catalog/intent/molecule-svg/run-fields) + productionized real routes on live REST/WS.
07. 06-production-hardening — shipped (2026-07-03)
    Reliable+versatile pivot, Phase 1 Tier 0 (reopen-nothing) + reliability. Repo hygiene + honest fork-and-run docs, env-driven origins, cost-gate reconciliation, CI, WCAG-AA a11y remediation + axe gate, Alembic baseline, cheap reliability patches (recoverable pause + oracle-fault tolerance + Modal propose n>1 + in-process durable resume). No new product features; got the shipped engine to production-grade polish.
    Slices: 01 repo-hygiene-and-docs ✓ · 02 ci-pipeline ✓ · 03 a11y-remediation ✓ · 04 axe-ci-gate ✓ · 05 alembic-baseline ✓ · 06 reliability-patches ✓ · 07 durable-resume ✓ — all shipped. Milestone complete.
08. 07-objective-ownership — shipped (2026-07-06)
    Phase 1 Tier 1 (make-it-yours + trust). Benchmark/exploratory mode split (the load-bearing invariant), FR-001 seed-SMILES plumbing fix, pluggable ScoringOracle + bundled presets, composed multi-term objective + constraints, molecule-quality/trust layer, provenance manifest (OD-5), lineage export, objective-authoring UI. Every exploratory feature gated so the G1 benchmark claim stays pristine (N6 holds).
    All 8 slices shipped → milestone complete.
09. 08-backend-systems-depth — shipped (2026-07-07)
    Backend systems depth + reframe. Convert the single-process asyncio monolith into a durable Postgres-backed producer→queue→out-of-process-worker system (SKIP LOCKED lease/heartbeat/reclaim), add LISTEN/NOTIFY cross-process live events, a persistent shared oracle-score cache, backpressure + REST gaps (pagination/idempotency), ops (Dockerfiles/compose/readyz), then reframe the repo's public README and ELI5 the domain. All-Postgres by design (no Redis/broker/k8s — deliberately rejected). G1 result + N6 preserved; docking is documented stretch.
    Slices: 01 credibility · 02 queue+worker (HARD GATE) · 03 events · 04 cache · 05 backpressure+REST · 06 ops (HARD GATE) · 07 reframe · 08 docking (stretch, uncommitted). Built via an autonomous dynamic Workflow with adversarial per-slice gates.
