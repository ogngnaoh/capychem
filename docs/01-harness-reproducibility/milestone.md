# Milestone 01 — Harness Reproducibility

> SPEC §9 Phase 1. Front-loaded the integration seams in `00-walking-skeleton`; this milestone proves the **eval contract** and the **observability contract** are real, not just that a loop runs.

## Goal

Prove CapyChem's eval and trace claims are trustworthy: the isolated harness reproduces a published Graph-GA PMO AUC-of-top-10 within tolerance through a canonical eval harness, and a real Langfuse trace of a loop run is viewable end-to-end.

## Scope

- **Canonical eval harness** — `packages/core/eval`: the authoritative AUC-of-top-10-mean-vs-oracle-calls implementation, plus a `capychem-eval` CLI entrypoint. This supersedes the "un-authoritative" running curve in `loop/logic.py` (which stays as the live-UI estimate).
- **Graph-GA reproduction** — run vanilla Graph-GA on QED (already wired) through the isolated `harness/` env; capture AUC-of-top-10 and diff it against the published PMO Graph-GA number **0.940** within **±0.02 absolute** (accept ≈0.92–0.96). Exact metric, baseline, and reproduction params are in `agent_docs/pmo-auc-and-baselines.md` (source-verified against the PMO paper Table 2 + `mol_opt` source).
- **Langfuse end-to-end** — provision real keys; confirm a nested trace (per-run → per-generation → per-node span) lands and is viewable for a loop run, verifying FR-014.
- **Valid-SMILES measurement** — build the measurement plumbing (RDKit validation + per-run rate tracking), exercised against the Graph-GA proposer. The measurement is the deliverable; the >80% pass/fail **gate check** rides with the LLM proposer in milestone 02.

## Non-goals

- **No LLM proposer.** Deferred to milestone 02; the >80% valid-SMILES *gate check* rides with it. Reproduction here is pure vanilla Graph-GA.
- **No beat-Graph-GA attempt.** Reproducing the baseline ≠ beating it. The first beat attempt is milestone 02 — and it must pick a task with *headroom* (e.g. `jnk3` 0.553, `zaleplon_mpo` 0.346), not QED, which the PMO paper disables as degenerate (oracle ceiling 0.948, reachable by random sampling). QED here is a plumbing smoke test only.
- **No analyzer step.** The differentiator lands in milestone 03.
- **No full 23-task sweep.** Reproduce on one task; the sweep is milestone 03.
- **No web/UI changes.** This milestone is harness / eval / observability — headless.
- **No Modal LLM endpoint.** Milestone 02. (The Modal *oracle* worker from slice 4 stays deployed, idle-cheap.)

## Slices

1. `01-reproduce-graph-ga` — **shipped (2026-06-16)**. Built `packages/core/capychem/eval` (canonical AUC-of-top-10) + the `capychem-eval` CLI; ran vanilla Graph-GA on QED through the harness. Verified AUC **0.9384** vs published **0.940** (diff −0.16%, within ±0.02). **The load-bearing deliverable** the walking skeleton skipped.
2. `02-langfuse-end-to-end` — planned. Provision real Langfuse keys (self-hosted via `infra/langfuse-compose.yml` or cloud); confirm a real nested per-generation trace lands and is viewable for a loop run (FR-014).
3. `03-valid-smiles-measurement` — planned. Plumb RDKit validation-rate tracking into the validate node and surface it per run; exercise against Graph-GA. Gate check vs the LLM proposer is explicitly milestone 02.

## Integration notes

- **Eval authority.** `packages/core/eval` becomes the single source of truth for AUC-of-top-10 (CLAUDE.md gotcha: "recomputing it ad hoc gives the wrong number"). `loop/logic.py`'s running curve is downgraded in role to a live-UI estimate only — do not let a second AUC definition drift in.
- **Harness seam reuse.** Reproduction runs Graph-GA through the same subprocess + JSON bridge exercised in walking-skeleton slices 1/2/4 (`packages/core/capychem/oracle.py` + `harness/capychem_harness/`). No new seam; never `import` from `harness/`.
- **Langfuse keys are secrets.** Land in `.env.local` (gitignored) / env only — never commit (CLAUDE.md critical constraint, SPEC §8.1). Provisioning is a user action; the slice can't close until keys exist.
- **Valid-SMILES feeds 02.** The per-run rate this milestone surfaces is the exact input the milestone-02 gate compares against >80% once the LLM proposer exists. Keep the field stable.
- **Slice independence.** Slices 1 and 3 both touch the loop/eval surface (`packages/core`) — sequence them. Slice 2 (Langfuse) touches `loop/trace.py` + infra + env and is parallelizable.

## Exit criteria

- Our QED AUC-of-top-10, computed by the canonical `packages/core/eval` harness and invoked via `capychem-eval`, lands within **±0.02** of the published PMO Graph-GA **0.940** (i.e. ≈0.92–0.96). A faithful `top_auc` (trapezoidal, `freq_log=100`, `finish=True`, `÷max_oracle_calls`) and `mutation_rate=0.067` are prerequisites — see the reference note.
- A real Langfuse trace for a loop run is viewable, showing the nested structure per-run → per-generation → per-node (FR-014 verified, no longer a no-op).
- A per-run valid-SMILES rate is measured and surfaced (gate check vs LLM deferred to milestone 02, documented as such).
