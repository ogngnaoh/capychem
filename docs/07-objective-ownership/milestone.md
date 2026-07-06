# Milestone 07 — objective-ownership

**Goal:** Turn the production-grade demonstrator into a tool a computational chemist can drive against **their own objective** — a pluggable oracle, a composed multi-term objective with constraints, bring-your-own compounds — all behind a visible benchmark/exploratory split so the shipped G1 claim stays pristine.

This is Phase-1 Tier 1 ("make-it-yours + trust") from `docs/superpowers/plans/2026-07-03-capychem-production-v1.md` and the design spec `docs/superpowers/specs/2026-07-03-capychem-production-reliable-versatile-design.md` (§6.A–6.C, §6.F–6.G, §7.A–7.F). Milestone 06 (production-hardening) is shipped; the engine is CI-gated, accessible, Alembic-migrated, and fault-tolerant.

## Scope
- **Mode split (the load-bearing invariant):** every run carries `mode` (`benchmark`|`exploratory`); any custom seed/oracle/objective/constraint ⇒ `exploratory`; only `benchmark` feeds the committed G1 numbers.
- **Objective ownership:** pluggable `ScoringOracle` protocol + registry; bundled presets (PMO, RDKit descriptors SA/QED/MW/logP/TPSA, ADMET-AI); a composed multi-term objective (weighted sum/product of transformed terms → one scalar in [0,1]) + SMARTS/property constraints.
- **Flexible inputs:** FR-001 seed-SMILES plumbing fix (bring your own starting compounds).
- **Trust layer:** per-candidate molecule-quality report (SA/QED/Lipinski/Veber/PAINS/Brenk), run-level diversity/novelty, a custom-oracle canary, a shared trust-gate module.
- **Provenance + outputs:** reproducibility manifest (OD-5: harness PyTDC version + model id + git SHA), lineage export (CSV/SDF).
- **Frontend:** objective-authoring UI, seed-import UI, quality display, mode badge on every run surface.

## Non-goals
- No expensive oracles **inside** the loop (docking = Phase-2 top-K rescore-report only; NG-3).
- No trained-per-task proposers (RL/REINVENT/GFlowNet — NG-4/N9); no true Pareto/NSGA-II (scalarization only — NG-5); no multi-agent planner/executor/critic (NG-6).
- No arbitrary-remote-code custom oracle — a typed Python-class plugin (OD-7), not `eval`'d uploaded code (NG-9).
- No auth / hosting / multi-user (NG-1/NG-2). No real-world efficacy claim, ever (N6/NG-8).

## Slices (execution order; see the plan for per-slice files + acceptance)
1. `07-01-run-mode-split` — `Run.mode`/`objective_json`/`constraints_json` (Alembic), API enforcement (`_gated_baseline`), `figure_canon` module, mode badge everywhere. **Must precede every feature below.** — shipped ✓ (eval ingestion needs no gate: `eval/*` runs its own loops, never ingests DB runs)
2. `07-02-seed-smiles-plumbing` — FR-001 6-layer fix + gen-0 branch + RDKit validation at `/runs`; custom seed ⇒ exploratory. — shipped ✓ (Alembic head `b4ea6a051441`; gen-0 tops up operator seeds from the shipped pool to `pop_size`)
3. `07-03-pluggable-oracle` — `ScoringOracle` protocol + registry; PmoOracle (parity test) + RDKit-descriptor + ADMET-AI presets; direction metadata. — shipped ✓ (`oracle/` package; direction threaded through sort/summary/AUC, default maximize byte-identical; loop/route consumption deferred to 07-04)
4. `07-04-objective-composition` — components/transforms/aggregator → [0,1]; loop consumption (default single-PMO byte-identical; composed ⇒ exploratory); `POST /objective/validate`. — shipped ✓ (split: constraints moved to 07-04b to keep each ≤2 pages)
4b. `07-04b-constraints` — hard SMARTS include/exclude (FilterCatalog PAINS/Brenk) at the validity gate; soft property bands = objective terms (no new code); constraint-starvation signal distinct from FR-003 plateau. — shipped ✓ (Alembic head `ed2d80a8ccda`: `runs.status` widened 16→32 for `constraint_starved`)
5. `07-05-quality-trust-layer` — per-candidate quality report + diversity/novelty + canary + shared trust-gate module (de-dup `_PARSE_RATE_FLOOR`). — shipped ✓ (Alembic head `0cc25e46d571`; backend only — quality DISPLAY + novelty seed_pop wiring deferred to 07-08)
6. `07-06-provenance-manifest` — OD-5: harness emits PyTDC version; persist model id/pin/git SHA; `GET /runs/{id}/manifest`. — shipped ✓ (Alembic head `38f369ef45a6`; `pytdc_version()` cached local probe; manifest built at finalize)
7. `07-07-lineage-export` — `GET /runs/{id}/export.{csv,sdf}` (lineage + quality); export UI. — planned
8. `07-08-objective-authoring-ui` — structured objective builder + seed-import + quality display + cockpit per-component reasoning + WS reconnect. — planned

## Integration notes
- **Sizing:** 8 slices exceeds the 7-per-milestone guideline — acceptable given the plan, but a session may split (e.g. fold 07-06 into 07-07 as "outputs", or spin 07-08 into its own UI milestone) if any slice grows past 2 pages.
- **Ordering:** 07-01 is the invariant carrier; every exploratory feature (07-02/03/04) ships with its `mode=exploratory` enforcement + test. All schema changes go through Alembic revisions chained from the current head (`f4251d568ae6`).
- **Benchmark regression gate:** the `benchmark`-mode eval must reproduce the committed G1 numbers unchanged — a hard test, not a convention.
- **Trust ships WITH the pluggable seam:** the quality/canary layer (07-05) is the headline reward-hacking defense; it lands in the same phase as custom oracles (07-03/04), not after.
- **Analyzer differentiator:** deepen it *with* the multi-term objective (per-component visibility — which term moved), per the design.

## Exit criteria
- A run can be launched with a pasted seed list + a 2-term composed objective + a SMARTS constraint entirely from the UI, is badged `exploratory` ("not benchmark-comparable"), and never contaminates the G1 numbers.
- `benchmark`-mode eval reproduces the committed 21-comparable G1 result unchanged.
- Every top-K candidate carries a quality report; the canary flags a known-degenerate on a new custom oracle; diversity/novelty surface per run.
- A run exports a valid SDF (RDKit round-trips) + CSV lineage + a citable manifest (real PyTDC version + model id + git SHA).
- axe/CI stay green; N6 + figure-canon honesty intact on every new surface (never "21/23").
