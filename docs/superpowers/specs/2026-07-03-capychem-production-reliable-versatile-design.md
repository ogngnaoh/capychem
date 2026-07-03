# Design Spec — CapyChem: Production-Grade, Reliable & Versatile Optimization Tool

**Status:** Draft for review
**Date:** 2026-07-03
**Author:** CapyChem session (post-milestone-05)
**Related:** PRD.md · SPEC.md · PROJECT.md · vault `claude-research-output/2026-07-03-capychem-reliable-versatile-production-roadmap.md` (rationale/landscape) · this is the buildable design.

---

## 1. TL;DR

Transform CapyChem from a benchmarked *demonstrator with a deliberately frozen engine* into a **polished, fork-and-run-locally, single-user tool with real (but narrow) utility in in-silico lead/hit optimization** — a computational chemist clones the repo, inserts env keys, and drives it against **their own objective**. This spec covers the change **end to end, backend and frontend**, in three phases. The load-bearing new capability is **objective ownership**: a pluggable oracle + composable multi-term objective + constraints, wrapped in **trust gates** (molecule-quality reporting, reward-hacking defenses) and **workflow fit** (seed import, lineage export, reproducibility manifest). The single most important design invariant is a visible **benchmark-mode vs. exploratory-mode** split so the new versatility never contaminates the shipped G1 "beats Graph-GA" claim. Every score remains an in-silico oracle score (N6); no real-world efficacy is ever claimed.

## 2. Context & positioning

- **Current state:** 5 milestones shipped; G1–G3 met; benchmarked on the 23-task PMO suite (beats/matches vanilla Graph-GA on all 21 comparable tasks, seed 42, 10k-call budget). Clean LangGraph loop with per-node Langfuse spans; LLM proposer (DeepSeek-v4-pro) + deterministic Graph-GA fallback (FR-005); per-run cost ledger + $50 cap; Next.js workbench (launch/watch-live/browse/compare); RDKit 2D rendering; strong WebSocket layer.
- **The pivot:** demonstrator → self-operated useful tool. Distribution = **local fork**; the user supplies keys and runs it. **No auth, no hosting, no multi-user, no per-IP rate-limiting** (dropped consciously).
- **Audience:** primary = a **computational chemist / cheminformatician** (the ~5–15% who already have a scoring oracle they trust and a real oracle-call cost constraint); secondary = the technical/recruiter reader of the repo. The honest goal is **plausible adoptability**, not mass adoption.
- **Honest ceiling (permanent, N6):** a *computational triage / hypothesis-generation assistant*, not a discovery engine. Better oracles/gates raise the ceiling; they never remove the in-silico label. Defensible claim: *"a genuinely usable in-silico lead/hit-optimization tool a computational chemist could drive against their own scoring function."*

## 3. Goals & non-goals

**Goals.**
- **G-A. Production quality:** verified accessibility (WCAG AA at the 1280px target), robust error/empty/loading states, CI-gated quality, data-safe migrations, honest docs, first-class fork-and-run DX.
- **G-B. Real utility (objective ownership):** a chemist can score against their own objective — a pluggable custom oracle, bundled real-ish presets, and a **composed multi-term objective with constraints**.
- **G-C. Reliability/trust:** every result carries a molecule-quality report and diversity/novelty signal; reward-hacking is actively defended; results are reproducible and provenance-stamped.
- **G-D. Versatility:** flexible inputs (bring your own compounds), flexible outputs (lineage export, manifest, SDK), and a documented roadmap of deeper method/agentic additions — each ablation-gated.
- **G-E. Honesty preserved:** the G1 benchmark claim stays pristine behind the mode split; N6 framing everywhere.

**Non-goals (this initiative).**
- **NG-1.** No auth / accounts / multi-user / per-user isolation (PRD §9, SPEC N8).
- **NG-2.** No hosted deployment; showcase = the repo + local run + GIFs.
- **NG-3.** No expensive oracles *inside the optimization loop* — docking (Vina/gnina/DiffDock) is **top-K rescore report only**, never per-generation; no GPU-heavy oracle as a default path.
- **NG-4.** No trained-per-task proposers (RL/REINVENT-policy, GFlowNet/Genetic-GFN) — reopens N9 (no novel ML training) and threatens finishability. Named honestly in the writeup as the field ceiling.
- **NG-5.** No true Pareto/NSGA-II multi-objective — breaks the single-scalar AUC-of-top-10 eval currency (G1/G6). Scalarization only.
- **NG-6.** No full multi-agent planner/executor/critic (SPEC Alt C) — scope explosion; the analyzer + self-critique carry the agentic story.
- **NG-7.** No novel ML architecture/training (N4); off-the-shelf models only (Chemprop *loaded*, not trained-for-you).
- **NG-8.** No real-world drug-discovery efficacy claim, ever (N6/PRD N6).
- **NG-9.** No arbitrary-remote-code "custom oracle" — a custom oracle is a typed adapter / local trusted script following the existing contract, not `eval`'d uploaded code. (Local fork means the user edits their own fork; no sandbox needed, but the interface is a declared plugin, not code injection.)

## 4. The central invariant — benchmark mode vs. exploratory mode

Every run carries a **`mode`**:

- **`benchmark`** — the frozen G1 path: one of the 23 PMO tasks as the *single canonical oracle*, the standard seed population, single-scalar AUC-of-top-10, PMO-comparable. Behaves exactly as today. This path is **not modified** by anything in this spec except read-only surfacing.
- **`exploratory`** — any custom seed population, custom/composed objective, custom oracle, or cross-run memory. Results are **clearly labeled "exploratory — not benchmark-comparable"** in the UI, in exports, and in the manifest. Exploratory runs never feed the committed G1 numbers or the reference baselines.

Enforcement: the API refuses to tag a run `benchmark` if it uses any exploratory feature; the eval harness only ingests `benchmark` runs; the UI badges the mode prominently on every run surface. This invariant is a hard acceptance criterion, not a convention.

## 5. Architecture overview (what changes)

New/expanded subsystems, all inside the existing `packages/core` + `apps/api` + `apps/web` structure (no new services):

```
Objective spec (composed) ─┐
Custom seed population ─────┼─► Loop (unchanged core) ─► Scoring engine ─► Oracle layer ─► {PMO | ADMET-AI | SA/QED | custom plugin}
Constraints (SMARTS) ───────┘         │                        │
                                      ▼                        ▼
                             Analyzer (per-component)   Quality/trust layer (SA/QED/PAINS/Lipinski, diversity, canary)
                                      │                        │
                                      ▼                        ▼
                             Persistence (+ objective, constraints, quality, mode, manifest fields; Alembic)
                                      │
                       ┌──────────────┼───────────────┐
                       ▼              ▼                ▼
                 REST (+ export/   WS (unchanged)   Python SDK / CLI
                 manifest/objective)
```

The optimization **loop mechanics stay intact**; new logic sits at the *objective/oracle boundary* (composition + constraints + custom plugin), the *reporting boundary* (quality/trust/export/manifest), and the *robustness boundary* (pause/resume/fault-tolerance). The WebSocket layer, the `top_auc` metric, and the Graph-GA fallback are preserved as-is.

---

## 6. Backend design

### 6.A Pluggable oracle architecture
- A `ScoringOracle` protocol: `score(smiles_list: list[str]) -> list[float | None]`, plus metadata (`name`, `version`, `direction`, optional `applicability_domain(smiles)->float`). Registered via an entry-point/plugin registry mirroring the existing harness-bridge contract in `packages/core/capychem/oracle.py`.
- **Bundled implementations:** (1) the existing PMO/PyTDC oracles (via harness subprocess); (2) **ADMET-AI** (CPU, pip, ~11ms/mol) exposing per-property predictions + ensemble uncertainty; (3) RDKit descriptor oracles (SA-score, QED, MW/logP/TPSA). These are the "useful out of the box without a BYO model" presets.
- **Custom oracle:** a documented plugin slot — a Python class implementing `ScoringOracle` (local, in the user's fork) **or** a local subprocess/REST endpoint following the typed JSON contract. **No eval of uploaded code** (NG-9).
- Budget accounting stays per-unique-call; when an objective mixes a free RDKit term with a costed ML term, the budget unit remains "oracle evaluation of a candidate" (see Open Decision OD-2).

### 6.B Objective composition engine
- An **objective spec** (persisted JSON): a list of components, each `{oracle, weight, transform}`, plus an aggregator (`weighted_sum` / `weighted_product`) → **one scalar** in `[0,1]`. Transforms: `sigmoid`, `double_sigmoid`/`step`, `reverse_sigmoid`, `value_map` (REINVENT4-parity). Single-scalar output **preserves AUC comparability** by construction.
- **Constraints layer** (separate axis): hard SMARTS include/exclude (scaffold-keep, toxicophore/PAINS-exclude via RDKit `FilterCatalog` / `rd_filters`-style sets) applied at the validity gate (same path FR-005 already exercises); soft property-range constraints (MW/logP/TPSA bands) as sigmoid/step components. A **"no candidate satisfies constraints"** signal is distinct from FR-003 plateau (avoid constraint-starvation masquerading as plateau).
- A composed objective or any constraint ⇒ `mode = exploratory`.

### 6.C Molecule-quality & trust layer
- **Quality report** attached to every top-K candidate (and available per-candidate on export): SA-score (RDKit `Contrib/SA_Score`), QED, Lipinski/Veber pass flags, PAINS/Brenk structural-alert hits. All RDKit-native, zero new dependency, computed at persistence time.
- **Diversity/novelty per run:** MOSES-style internal diversity (mean pairwise Tanimoto on Morgan FPs) + novelty vs. the seed population — surfaced in the run summary; flags mode collapse.
- **Custom-oracle canary:** before an exploratory run on a *new* plugin oracle, score a small fixed probe set of known-degenerate molecules (long alkyl chains, single-atom repeats, etc.); warn if any score implausibly high. A mitigation, framed as such — not a guarantee.
- **Optional penalized objective** (Phase 2): a toggle to fold an SA/QED/PAINS penalty into the composite so the loop optimizes *against* degenerate exploits, not just detects them after.
- **Applicability-domain flag** (Phase 2, ML oracles): surface ADMET-AI's existing ensemble uncertainty + a k-NN-to-training-set distance; no new model training (N4-safe).
- Reuse the proven `_PARSE_RATE_FLOOR`-style "verdict-guarding" pattern in `eval/beat.py`/`verdict.py` as the home for any trust gate.

### 6.D Reliability & robustness
- **Recoverable pause:** catch `HarnessError` distinctly in `apps/api/.../runner.py::_drive`; introduce a `paused` run status (free-text status column — no schema break); surface to the operator with retry, instead of hard `errored`. Closes PRD edge-case-2.
- **Oracle-path fault tolerance:** degrade a transient `HarnessError`/timeout to "skip this generation, keep budget, log + surface," mirroring the proposer's `TransientProposerError` pattern — the oracle path currently has none.
- **In-process durable resume:** reconstruct `mol_buffer` + `gen_index` from persisted `Candidate`/`Generation` rows on restart (data already in Postgres); the startup sweep marks orphans `paused`, resumable, instead of `stopped`.
- **Modal `propose` n>1 fix:** port the `direct` backend's `asyncio.gather` single-`n` fan-out (`proposer.py`) into `apps/worker/app.py`; optional warm-pool kwargs to address cold-start. (Modal remains optional for a forker; `direct`/`stub` runs without it.)
- **Cost-gate:** reconcile SPEC §8.3 to the shipped flat cap, *or* implement the projective pre-generation check — decide in OD-3.
- **CI:** GitHub Actions running pytest/mypy/ruff + pnpm test/tsc/eslint + axe on PR; free `stub`/`graph_ga` smoke; badge in README. Closes the SPEC §10 CI claim.

### 6.E Search & agentic depth (Phase 2, each ablation-gated)
- **Analyzer per-component visibility + explore/exploit scheduling:** feed the analyzer per-term deltas (so it reasons "gain came from SA, not QED"); let it drive temperature / `CONDITIONED_FRACTION` / plateau strategy-switch instead of fixed constants. Extends the differentiator; deepening objectives and the analyzer is one workstream.
- **Surrogate / active-learning pre-filter:** train an in-run boosted-tree/GP on already-scored candidates; rank LLM/GA proposals; spend real oracle calls only on the top slice. Attacks the actual AUC-per-oracle-call metric; off-the-shelf ML (N9-safe); compatible with `top_auc` (counts only scored candidates).
- **BYO-QSAR oracle:** load an existing Chemprop checkpoint as a `ScoringOracle` (N4-safe: load, don't train).
- **Roadmap (behind ablations):** SELFIES optional representation; fixed-scaffold/R-group-constrained mutation (restrict edit site, not a new architecture); cross-run memory (pgvector/RetMol, **default OFF**, seeded from CapyChem's own sweep); analyzer self-critique pass.

### 6.F Data model & migrations
- **New/changed:** `Run.mode` (`benchmark`|`exploratory`); `Run.objective_json` (composed spec) and `Run.constraints_json`; `Run.seed_source` + wire **`seed_smiles` through `CreateRunRequest`/`RunConfig`/gen-0** (the FR-001 bug fix); `Candidate` quality fields (SA/QED/Lipinski/PAINS) or a linked `CandidateQuality`; run-level diversity/novelty in `summary_json`; `OracleCall.oracle_version`; manifest fields (git SHA, model id, harness/PyTDC pin); `Run.project_id`/`tags` (Phase 2 campaigns).
- **Alembic:** introduce migrations + commit the initial revision; replace the drop-recreate dev pattern (real local runs must survive a schema bump). Wire `alembic upgrade head` into startup/deploy docs.
- **Provenance:** confirm the harness JSON contract can emit a PyTDC version string (OD-5) and whether the LLM model id is capturable per run.

### 6.G Interfaces (REST + SDK + CLI)
- **REST additions:** `POST /objective/validate` (preview a composed objective + constraints); seed-import handling on `POST /runs`; `GET /runs/{id}/export.csv`, `.sdf` (full lineage: gen index, parent, hypothesis-at-birth, quality fields), optional `.parquet`; `GET /runs/{id}/manifest`; quality/diversity in `GET /runs/{id}`; N-way `GET /compare?ids=` (generalize the pairwise resampler); campaign endpoints (Phase 2).
- **Python SDK (Phase 2):** a documented `import capychem` entry — `optimize(objective, budget, seed=..., oracle=...)` wrapping the loop; `load_run(id) -> DataFrame`. Package `packages/core` as importable/pip-installable.
- **CLI:** the existing `capychem-run`/`capychem-eval` documented as first-class headless entry points.

---

## 7. Frontend design

### 7.A Objective-authoring UI (the biggest new surface, Phase 1)
A structured builder in the workbench: pick oracles (bundled presets + registered custom), set weights + transforms, add SMARTS/property constraints, with a **live preview** of what the composite scores and what gets penalized. Editable "resolved plan" mirror as today. Produces the objective spec consumed by 6.B. For `benchmark` mode this collapses to the existing single-task pick.

### 7.B Seed-population import (Phase 1)
Upload/paste SDF/SMILES/CSV; RDKit-validate at the boundary; show accepted/rejected with reasons. Wires to the fixed seed-SMILES bug fix (6.F). Any custom seed ⇒ exploratory badge.

### 7.C Molecule-quality display (Phase 1)
On each top-K tile: SA-score, QED, Lipinski/Veber pass, PAINS/Brenk flags as compact badges alongside the existing 2D structure + SMILES + score. Run summary shows diversity/novelty. Makes hits *credible*, not just high-scoring.

### 7.D Export UI (Phase 1)
Download buttons for CSV/SDF (full lineage) and the reproducibility manifest, from the run-detail view.

### 7.E Cockpit / live improvements (Phase 1)
- **Accessibility remediation (real WCAG failures found):** fix primary-button text contrast (fails AA in both themes), light-mode focus ring (~1.54:1); add a visually-hidden `aria-live` region for live-run updates (the headline feature is currently silent to screen readers) + `role="alert"` on async errors; stop silently swallowing catalog/runs fetch errors; add skip-to-content link, per-route `<title>`s, `aria-sort` on the runs table, trim molecule alt text.
- **WS reconnect + connection state:** distinguish `run.complete` from a dropped socket; reconnect-with-backoff or (floor) a clear "connection lost + manual refresh" state, `aria-live`-announced. Cold-start "waking the model (~30s)" copy.
- **Analyzer per-component reasoning:** surface which objective term moved (pairs with 6.E).

### 7.F Mode indicator + honesty (all phases)
A prominent **benchmark / exploratory** badge on every run surface; exploratory runs carry "not benchmark-comparable." In-silico labeling on every score-bearing surface (already consistent — extend to new oracles). Scope the "WCAG AA" doc claim to the 1280px target viewport (Reflow 1.4.10 honesty).

### 7.G Campaigns + N-way compare (Phase 2)
"Investigations" grouping (project/tags), roll-up view, and >2-run overlay (generalize the existing resampler).

---

## 8. Reliability & scientific rigor

- **Multi-seed variance (Phase 2):** run 3 seeds on 4–5 representative tasks, report mean ± std + a paired significance test — converts the flagship claim from "true for seed 42" to "true in expectation" (PMO's own standard). **Not** a full 23×N re-sweep (finishability + budget).
- **Reproducibility manifest:** a citable, re-runnable record (config, seed, oracle/harness version, model id, git SHA, Langfuse trace URL) exported per run.
- **Reward-hacking discipline:** quality report + canary + optional penalized objective + diversity/novelty are the layered defense; the pluggable oracle *increases* this risk, so these ship *with* it, not after.

## 9. Fork-and-run DX

- A rewritten **root README** (honest positioning, the defensible claim, a quickstart) and a real **`apps/web/README.md`**.
- A complete **`.env.example`** documenting every key (DeepSeek/Modal/Langfuse/Postgres) with `openssl rand -hex 32` instructions for Langfuse secrets; **env-driven `ALLOWED_ORIGINS`**.
- **Quickstart that runs out of the box on the `stub`/benchmark path** (no keys needed to see it work); keys unlock the real LLM proposer + custom/preset oracles. Local `docker compose` bring-up for Postgres (+ optional Langfuse). Explicitly **no auth/hosting**.
- A `CONTRIBUTING` + documented plugin-authoring guide for custom oracles.

## 10. Phasing (maps to milestones)

- **Phase 1 — "v1: production-grade + make-it-yours + trust" (Tier 0 + Tier 1).** §6.A–6.D + 6.F–6.G(REST/export/manifest) + §7.A–7.F + §9. This is the buildable v1 that delivers real, honest utility. Multi-milestone.
- **Phase 2 — "versatility + rigor" (Tier 2, each ablation-gated).** §6.E + §7.G + SDK + multi-seed + campaigns + BYO-QSAR + docking-as-rescore-report.
- **Out of scope / documented future work (Tier 3).** NG-3–NG-6 items — named honestly in the writeup, not built.

## 11. Cross-cutting: N6 & honesty

- Every score-bearing surface keeps in-silico/oracle/benchmark labeling; new oracles inherit it.
- Figure canon unchanged and never restated wrongly: beats/matches vanilla Graph-GA on all **21 comparable** PMO tasks (seed 42, 10k), 2 of 23 excluded-for-cause; no SOTA/multi-seed claim (until Phase-2 multi-seed lands, then reported honestly). Never "21/23."
- The mode split is the mechanism that lets "versatile" and "honest benchmark" coexist.

## 12. Testing & validation

- **Unit/integration (pytest):** objective composition + transforms; constraint application + constraint-starvation signal; quality-metric computation; canary; recoverable-pause + oracle-fault-tolerance + durable-resume paths; mode-enforcement (a composed/custom run cannot be `benchmark`).
- **Eval:** the `benchmark`-mode path reproduces committed G1 numbers unchanged (a regression gate).
- **Frontend:** vitest for the objective builder + import + quality display; Playwright + **axe-core** CI gate (fail on serious/critical) across routes in light+dark; keyboard/SR verification plan.
- **Phase-2 ablation gates:** SELFIES, surrogate pre-filter, analyzer explore/exploit, self-critique — each must show a measured AUC effect on a budget-300-scale ablation before it's resourced (the slice-06 discipline).

## 13. Open decisions (for review)

- **OD-1. Phase-1 depth of backend robustness:** cheap patches (recoverable pause + in-process durable resume) — recommended — vs. the full durable-run-loop-on-Modal (bigger, strongest systems flex; probably overkill for a single-user local tool).
- **OD-2. Budget unit under mixed-cost objectives:** keep "oracle evaluation" as the unit, or move to cost-denominated budget once objectives compose free + costed terms?
- **OD-3. Cost-gate:** reconcile the SPEC text to the flat cap (cheap) or implement the projective 1.5× pre-generation check (more rigorous)?
- **OD-4. Quality gate — hard vs. soft:** drop PAINS/Lipinski failures pre-oracle (saves budget, changes "top-10") or annotate-only (keeps comparability)? Recommendation: per-run toggle; annotate-only in benchmark mode.
- **OD-5. Provenance availability:** does the harness JSON contract already carry a PyTDC version string, and is the LLM model id capturable per run? (Verify before promising the manifest.)
- **OD-6. Docking-as-rescore in Phase 1 or 2?** Recommendation: Phase 2 (finishability).
- **OD-7. Custom-oracle interface shape:** Python-class plugin (simplest for a fork) vs. local subprocess/REST endpoint (language-agnostic). Recommendation: ship the Python-class plugin first, subprocess contract as a follow-on.

## 14. Risks

- **Finishability/scope:** Phase 1 is a genuine multi-milestone build; sequence Tier 0 (cheap, no-reopen) first, then Tier 1. Don't start Phase 2 until v1 ships.
- **Benchmark contamination:** the mode split must be enforced in code + tests, not just documented — the whole honesty story depends on it.
- **N6 drift:** as the tool gets more "useful," resist any copy that implies real-world efficacy; the defensible claim is fixed.
- **Reward hacking on custom oracles:** the pluggable seam's headline risk; the trust layer (6.C) is mandatory in the same phase, not deferred.
- **Subagent execution:** per prior session learning, run any build subagents via file-write handoff / synchronously and independently re-verify their claims.
