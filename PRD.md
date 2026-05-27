# PRD: CapyChem

**Status:** Draft
**Last updated:** 2026-05-26

## 1. Problem

A drug-discovery scientist exploring a new objective faces an enormous chemical space and a small budget of expensive scoring oracle calls. Naive random or exhaustive search wastes the budget before finding good hits. Existing autonomous tools propose molecules generation after generation but do not *reason* over what worked in the previous generation, so they leave information on the table. The scientist needs an assistant that runs a closed-loop design–score–analyze–redesign cycle, learns from each generation's results, and returns the best molecules per oracle call — not the best molecules per hour of compute.

## 2. Target users

- **Primary:** Drug-discovery scientist doing first-pass hit-finding or lead-optimization against a defined molecular objective. Comfortable reading SMILES and 2D structures; expects standardized in-silico benchmarks as ground truth at this stage.
- **Secondary:** ML / optimization researcher comparing sample-efficient black-box optimization methods against published baselines.

## 3. Goals & success metrics

- **G1 — Beat the strong baseline.** Beat the vanilla Graph-GA baseline on **≥6 of 23 PMO benchmark tasks** by AUC of top-10 mean score under a 10,000-oracle-call budget. **By 2026-09-15.**
- **G2 — Closed loop runs end to end.** The full propose → score → analyze → redesign cycle runs to completion on any selected benchmark task within the 10,000-call budget, at a compute cost equivalent of **under ~$50 per run**. **By 2026-08-04.**
- **G3 — Operator surface complete.** The web app supports the four primary flows (launch, watch-live, browse results, compare two runs) across the full 23-task benchmark surface. **By 2026-09-15.**

## 4. Non-goals

- **N1** No patient or clinical data, ever. The system is strictly upstream of patients.
- **N2** No wet-lab automation or hardware control. In-silico only.
- **N3** No proprietary or inaccessible datasets. Public / permissively-licensed only.
- **N4** No novel ML architecture research. The contribution is in engineering the closed-loop agent, not in new model design.
- **N5** Not a chemistry-expertise product. Correctness is delegated to standard benchmark oracles; the assistant offers no chemistry advice of its own.
- **N6** No claim of real-world drug-discovery efficacy. Every score is an in-silico oracle score and is reported as such.

## 5. User stories

### Story 1 — Launch a run
**As a** drug-discovery scientist **I want** to configure and start an optimization run **so that** I can target a chosen molecular objective with a known budget.

**Acceptance scenarios:**
- *Given* I am on the home view, *when* I select a benchmark task, set an oracle-call budget and a mutation-strategy choice, and click Start, *then* the run is created and I am routed to its live view.
- *Given* I submit a budget of zero or no task selected, *when* I click Start, *then* the system refuses to start the run and tells me exactly which input is invalid.
- *Given* another run is currently in progress, *when* I start a new run, *then* the new run is accepted and queued or run in parallel without interfering with the in-progress run's results.

### Story 2 — Watch a run live
**As a** scientist **I want** to see a run's progress in real time **so that** I can stop early if it plateaus.

**Acceptance scenarios:**
- *Given* a run is in progress, *when* I open its live view, *then* I see the current generation, the best-so-far score, oracle calls consumed, and the latest analyzer hypothesis, all updating within seconds of each new generation event.
- *Given* the top-K score has not improved for the configured plateau window, *when* the plateau is detected, *then* the live view surfaces a plateau signal and offers a stop control.

### Story 3 — Browse run results
**As a** scientist **I want** to inspect a completed run's top molecules **so that** I can decide which to explore further.

**Acceptance scenarios:**
- *Given* a completed run, *when* I open its detail view, *then* I see its top-K molecules each rendered with 2D structure, SMILES, and score, plus an AUC-of-top-K curve over oracle calls and the full per-generation analyzer-hypothesis history.
- *Given* I want deeper step-by-step trace detail, *when* I click the trace link, *then* I am taken to an external observability surface showing every loop decision.

### Story 4 — Compare two runs
**As a** scientist **I want** to compare two runs side by side **so that** I can judge which configuration worked better.

**Acceptance scenarios:**
- *Given* two completed runs, *when* I open the compare view for them, *then* I see overlaid AUC curves, side-by-side top molecules, and per-run oracle-call and compute-cost stats.

## 6. Functional requirements

- **FR-001** System MUST allow a user to configure a run — benchmark task, oracle-call budget, initial seed population (or default), mutation-strategy choice, plateau-window — and start it from the web interface.
- **FR-002** System MUST enforce the configured oracle-call budget; the loop MUST stop when the budget is exhausted, with the partial generation counted and persisted.
- **FR-003** System MUST stop a run when the top-K score has not improved for the configured plateau window.
- **FR-004** For each generation, the System MUST produce a set of candidate molecules using a model-driven proposer, validate every candidate, and discard or repair invalid candidates before scoring.
- **FR-005** System MUST fall back to a deterministic graph-edit mutation operator whenever the model proposer emits an invalid candidate, so that the loop sustains full throughput on invalid output.
- **FR-006** System MUST score every validated candidate against the selected benchmark oracle and record the score with provenance: which proposer produced it, which parent molecule (if any), and which generation it belongs to.
- **FR-007** Between generations, System MUST produce an analyzer hypothesis summarizing what improved the score and condition the next proposal on it.
- **FR-008** System MUST persist every run's full history: configuration, candidates, scores, oracle calls, analyzer hypotheses, and final summary.
- **FR-009** System MUST push live updates to the run's open view as each generation completes and as new analyzer hypotheses are produced.
- **FR-010** System MUST provide a list view of all runs, sortable and filterable by status, best score, oracle-call count, and timestamp.
- **FR-011** System MUST provide a run-detail view showing top-K molecules (2D structure + SMILES + score), the AUC-of-top-K curve over oracle calls, the full analyzer-hypothesis sequence, and a link to the external trace.
- **FR-012** System MUST provide a compare view that takes two runs and shows overlaid AUC curves, side-by-side top molecules, and per-run oracle-call and compute-cost stats.
- **FR-013** System MUST track and persist per-run compute-cost equivalents and surface them in the run-detail and compare views.
- **FR-014** System MUST expose each run's complete decision trace to an external observability surface so that every step is auditable.
- **FR-015** System MUST refuse to start a run when no benchmark task is selected, when the budget is non-positive, or when the system is otherwise misconfigured, and MUST explain the refusal to the user.

## 7. Non-functional requirements

- **Sample efficiency:** AUC of top-10 mean score under the 10,000-call budget is the primary measure, per G1.
- **Cost discipline:** A complete 10,000-call run completes under ~$50 in compute-cost equivalents.
- **Reliability:** A single run sustains a 10,000-call loop end to end without manual intervention.
- **Live-update latency:** The watch-live view reflects a new generation event within ~2 seconds of its occurrence at the 95th percentile.
- **Observability:** Every loop decision (proposal, score, analyzer hypothesis, fallback) is traceable end to end.
- **Demo responsiveness:** The web app renders cleanly on a 1280-pixel-wide screen with the run-detail and compare views fully visible without horizontal scroll.

## 8. Edge cases

- The model proposer emits invalid candidates on every step → fallback graph-edit mutation operator must keep the loop running at full throughput.
- The oracle worker pool becomes temporarily unavailable → the run pauses in a recoverable state rather than losing work.
- The analyzer returns an empty, malformed, or off-topic hypothesis → the system falls back to a neutral or last-good hypothesis instead of stalling.
- The oracle-call budget is exhausted mid-generation → the partial generation is persisted and counted; the run terminates cleanly.
- Two concurrent runs target the same benchmark task → results are isolated; resource allocation is fair.
- A run is started, then abandoned by the operator → the run continues to budget exhaustion or plateau and remains browseable afterward.

## 9. Assumptions & dependencies

- The PMO benchmark suite is treated as the authoritative measurement; its oracle scores are accepted as ground truth for the purposes of this work.
- Cloud GPU compute is available for the proposer model under the cost gate stated in G2.
- The operator is comfortable reading SMILES and 2D molecular structures.
- The single primary persona is the only user class; multi-user collaboration is out of scope (no auth surface).

## 10. Open questions

- Default plateau-window length and threshold — to be tuned during early runs; configurable per run from day one.
- Whether to expose raw oracle-call cost per generation to the operator or only a per-run summary — defer to user testing post-MVP.
