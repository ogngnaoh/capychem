# CapyChem — Project Context Bundle (v2, verified)

> **Purpose.** Handoff from a scoping session, structured to feed the **doc-system** skill (Mode 4, full setup). Maps onto doc-system's interview protocol so it can produce SPEC.md / CLAUDE.md / seed ADRs **without re-interviewing settled questions**.
>
> **v2 changes (delta from v1):** all `[judgment]` external claims have been verified against a companion research report and are now tagged `[VERIFIED]` or `[CORRECTED]`. Four material changes: (1) kill-switch recalibrated — Graph GA is a *strong* baseline, not a trivial one; (2) the **analyze** step elevated as the genuine differentiator (it is *absent* from the MOLLEO reference); (3) the **backend-headline weighting flagged as a re-decision point** — the de-risked MVP is agentic/eval-heavy and backend-thin; (4) two new operational risks added (old dependency surface, LLM token cost).
>
> **Tag legend:**
> - `[LOCKED]` — decided in scoping; honor it.
> - `[VERIFIED]` — confirmed against the research report (papers / OSS repos / sources).
> - `[CORRECTED]` — was wrong or imprecise in v1; fixed here.
> - `[OPEN]` — decide at doc time; recommendation included as input.
> - `[RE-DECIDE]` — a previously-locked item that verified evidence calls into question; resolve consciously before spec.

---

## 0. One-liner

**CapyChem is an autonomous closed-loop molecular optimization agent** — an LLM-driven agent that runs design → score → **analyze** → redesign cycles over black-box scoring oracles, finding high-scoring molecules in as few oracle calls as possible. `[LOCKED]`

Precise technical framing (use this in any writeup, per `[CORRECTED]` guidance): *sample-efficient black-box optimization over chemical space, benchmarked on standardized in-silico oracles.* The "drug-discovery copilot" framing is the user-facing story; the technical substance is sample-efficient optimization. Do **not** claim real-world drug-discovery efficacy. `[CORRECTED]`

---

## 1. Project identity (→ doc-system: Project identity)

- **What it does:** Optimizes molecules toward a target objective via an autonomous agentic loop over black-box oracles, maximizing score per oracle call. `[LOCKED]`
- **Who it's for (stated):** Drug-discovery scientists, as a first-pass hit-finding / lead-optimization assistant. `[LOCKED]`
- **Who it's *really* for:** Portfolio flagship for the builder's big-tech **SWE internship** applications (general SWE + AI/ML tracks). Drug discovery is the *frame*, not the substance; the audience is an intern recruiter / HM skimming a GitHub repo + writeup. `[LOCKED]`
- **Builder profile:** Strong SWE; multi-framework agentic experience (shipped demos, not production-grade agentic systems); **zero chem/bio background** — domain knowledge cannot be assumed. Solo. Cloud GPU available (Modal-style). `[LOCKED]`

---

## 2. The core loop (what actually gets built)

1. **Propose** — generate/modify candidate molecules (LLM-driven SMILES/SELFIES edits, with a deterministic Graph-GA fallback for invalid output).
2. **Score** — evaluate candidates against a black-box oracle (PMO/TDC oracle function).
3. **Analyze** — LLM reasons over the generation's results (e.g. top-k vs bottom-k), forms a hypothesis about what's improving score, and conditions the next proposal prompt on it.
4. **Redesign** — propose the next batch, balancing explore/exploit under a fixed oracle-call budget.
5. **Stop** — terminate on budget exhaustion or plateau.

**Critical `[VERIFIED]` insight:** the reference architecture (MOLLEO) implements steps 1–2–4 only — it is *purely* an LLM mutation operator inside Graph GA, with **no analyze step**. Step 3 (the analyzer agent) is therefore CapyChem's genuine differentiator and the thing that earns both the "closed-loop" and "agentic depth" claims. Without step 3, CapyChem is a MOLLEO clone; with it, it's MOLLEO + a closed analysis loop. *(Week-one confirm: read MOLLEO's source to verify the analyze gap before building the narrative on it.)* `[CORRECTED]`

---

## 3. Tool / oracle palette (the "suite of workflows")

| Tool | Role | Status | Notes |
|---|---|---|---|
| **PyTDC / PMO oracle functions** | MVP oracle (the "score" step) | `[VERIFIED]` | CPU, cheap, ground-truth. This is the MVP oracle — **not** live docking. |
| **ADMET-AI** | Auxiliary oracle (stretch) | `[VERIFIED]` | `swansonk14/admet_ai`, MIT, CPU-friendly, pip-installable. Best stretch oracle. |
| **AutoDock Vina** | First "real" expensive oracle (stretch) | `[VERIFIED]` | Apache-2.0, `pip install vina`, CPU. Needs PDBQT prep (Meeko/OpenBabel). |
| **smina** | Docking alt | `[VERIFIED]` | GPL fork; faster local minimization. License hygiene: GPL. |
| **DiffDock** | ML docking | `[VERIFIED]` | GPU-heavy (16GB+ VRAM), GPL-style. **Scope creep — only if docking is a core deliverable.** |
| **RDKit** | Cheminformatics substrate | `[VERIFIED]` | BSD-3; underpins everything (SMILES, fingerprints, QED, SA, Graph-GA ops). |

MVP oracle = a PMO/TDC benchmark function. Richer/expensive oracles (ADMET-AI → Vina → DiffDock, in that order of effort) are **stretch** — *unless* backend is pulled forward as the headline (see §10 `[RE-DECIDE]`). `[CORRECTED]`

---

## 4. Scale signals (→ doc-system: Scale classification)

- **Size/duration:** months, multi-session, multiple deployable subsystems. `[LOCKED]`
- **Subsystems:** agent runtime / loop controller, eval harness, oracle/tool layer, (optional) model-serving platform, API/backend, observability. `[LOCKED]`
- **Recommended doc-system scale: Very Large.** Multi-session + multiple deployable steps + own non-goals + a genuinely fiddly dependency surface (see §5) → classify Very Large; do not go below Large. `[VERIFIED]`

---

## 5. Tech stack (→ informs SPEC one-liners + ADRs)

Most of this hardened from `[judgment]` to `[VERIFIED]`. Each still becomes an ADR with alternatives at doc time.

| Layer | Recommendation | Status |
|---|---|---|
| Eval substrate | **PMO `wenhao-gao/mol_opt`** (MIT) + **PyTDC** oracles. Subclass its `BaseOptimizer`. | `[VERIFIED]` |
| Reference architecture | **MOLLEO** (`zoom-wang112358/MOLLEO`) — **read-only, no LICENSE file; reimplement clean, do not copy code.** | `[VERIFIED]` |
| Agent orchestration | **LangGraph** (stateful, branching, checkpointed loop control). | `[VERIFIED]` |
| Observability / tracing | **Langfuse** (MIT, self-hostable, OTel-native, free tier) over LangSmith — no lock-in, works with raw SDKs or LangGraph. | `[VERIFIED]` upgrade from `[OPEN]` |
| Proposal LLM | GPT-4o or Claude for MVP; **open-model fallback (BioT5 / Llama-class) if token cost > ~$50/run.** | `[VERIFIED]` + new cost gate |
| Model serving / inference | **Modal** (Python-decorator serverless GPU; matches stated access). Used for expensive oracles + sweeps. | `[VERIFIED]` |
| Data store | Postgres or SQLite for run/result metadata. | `[OPEN]` |
| API surface | FastAPI-class. | `[VERIFIED]` (sensible) |
| Deployment target | Modal + container. | `[VERIFIED]` (sensible) |

**New `[VERIFIED]` risk — dependency surface:** `mol_opt` pins an *old* stack (PyTDC 0.3.6, Python 3.7–3.10, PyTorch 1.10.2 per its README). Use a dedicated pinned conda env for the harness; isolate it from the modern agent/serving code. This is a real week-one hazard. `[CORRECTED]`

---

## 6. Irreversible decisions + alternatives (→ doc-system: seed ADRs)

### ADR-candidate A — Anchor: autonomous closed-loop molecular optimization `[LOCKED]`
- **Decision:** closed-loop optimization agent, not a pipeline-with-agent or one-shot tool-use agent.
- **Alternatives rejected:** distributed virtual screening (agent decorative, reads as data-infra, generic); ChemCrow-faithful one-shot tool agent (less agent-native, weaker sequential-decision story); multi-agent planner/executor/critic (scope risk → stretch); interactive human-in-the-loop workbench (dilutes the autonomous demonstration).
- **Consequences:** agent is the product (good); eval is structurally load-bearing (cost); highest scope-risk option → hard MVP boundary required.
- **`[VERIFIED]` update:** reimplementation maturity is *higher* than assumed — MOLLEO provides a near-exact reference architecture.

### ADR-candidate B — Eval via PMO + TDC oracle benchmarks `[VERIFIED]`
- **Decision:** measure by **sample efficiency on PMO** (23 single-objective tasks, 10,000-oracle-call budget, metric = AUC of top-10 mean score vs. oracle calls), using PyTDC oracles.
- **Alternatives rejected:** bespoke eval (needs chemistry intuition the builder lacks; not comparable; not credible).
- **Consequences:** de-risks the single biggest threat (correctness is checkable without chemistry knowledge); results are comparable + screenshot-able.
- **`[VERIFIED]` nuance:** pin *legacy* PyTDC for PMO compatibility (active dev has forked to `pytdc-nextml`, ICML 2025). PMO is single-objective; multi-objective lives in a separate branch — note it if the differentiator goes multi-objective.

### ADR-candidate C — LLM-driven proposal + analysis `[VERIFIED] / [CORRECTED]`
- **Decision:** LLM drives the proposal (mutation operator, MOLLEO-style) **and** the analysis (the step MOLLEO lacks). Deterministic Graph-GA mutation is the fallback for invalid LLM output (critical — without it, AUC collapses).
- **Baselines (corrected reality):** Graph GA is a **strong** baseline, not trivial. SOTA ceiling = **Genetic GFN, 16.213 AUC** (a *non-LLM* method); REINVENT ≈ 15.185; MOLLEO's real result = beats vanilla Graph GA on 9/12 tasks *with GPT-4*. The honest value prop is **flexibility, explainability, and the analysis loop — not beating SOTA.**
- **Consequences:** this is the agentic-depth + "reimplementation-plus" story; risk is that LLM proposal underperforms classical baselines (see kill-switch §9).

### ADR-candidates D–G — `[OPEN]` stack decisions
Agent framework, serving/inference, observability, data store — each an ADR with alternatives at doc time (defaults in §5).

---

## 7. Non-goals (→ doc-system: Non-goals; ≥3) `[LOCKED]` (+1 new)

1. **No patient or clinical data, ever.** Strictly upstream of patients.
2. **No wet-lab automation / hardware.** In-silico only.
3. **No proprietary/inaccessible datasets.** Public / permissively-licensed only.
4. **No novel ML architecture.** Reimplementation demonstrating engineering rigor; differentiator is engineering, not novelty.
5. **Not a chemistry-expertise product.** Correctness delegated to oracles/benchmarks + LLM.
6. **No claim of real-world drug-discovery efficacy.** All oracles are computational; CapyChem optimizes in-silico scores, full stop. `[CORRECTED]` (new, per verification)

---

## 8. Success criteria / "done" (→ doc-system: SPEC success criteria) `[CORRECTED]`

**MVP (hard boundary):**
- Single-objective loop against one PMO oracle, one LLM proposal strategy, the Graph-GA fallback wired.
- Eval: **beat vanilla Graph GA on ≥6 of 23 PMO tasks** by AUC top-10. *(Stretch: match MOLLEO's 9/12 on its reported subset.)*
- **Track two budgets:** the 10K oracle-call budget AND LLM call/token cost. Report both.
- End-to-end traced runs (Langfuse), an observability surface, a reproducible-run harness, an API.

**First differentiation milestone (pull into MVP if possible):** the **analyzer agent** (step 3) — the MOLLEO gap. This is what makes the project distinctive.

**Stretch:** multi-objective (Pareto + multi-objective prompting); expensive oracles (ADMET-AI → Vina on Modal); proposer/critic multi-agent split; memory/RAG over past successful mutations (the ExLLM angle).

**"Impressive" for the real audience:** a reviewer opens the repo and sees a coherent agent with rigorous, baseline-comparable eval and clean system design — legible *without* drug-discovery knowledge.

---

## 9. Kill-switch & decision gates (→ doc-system: SPEC kill-switch) `[CORRECTED]`

Tiered, replacing v1's mis-calibrated "beat random/Graph-GA":

- **Week-1 feasibility gate:** stand up `mol_opt` (old conda env) and reproduce one Graph-GA PMO result; get **>80% valid-SMILES rate** from the chosen LLM on a simple prompt. Fail → fix env/prompt/model before proceeding.
- **Cost gate:** if LLM cost to reach 10K oracle calls > ~$50/run → switch to a smaller/open model.
- **Week-8 bar:** beat Graph GA on **≥3 PMO tasks** by AUC top-10. Fail → **pivot to LLM-as-analyzer-only** (thinner but defensible), do *not* abandon.
- **True anchor-kill (rare):** only if even the analyzer-only angle shows no value *and* the harness fundamentally won't run. Much higher bar than v1.

---

## 10. Discipline mapping & hiring narrative (→ context for SPEC "why")

Stated weighting: **backend (headline) > agentic (growth) > eval (load-bearing).** `[LOCKED]` — **but see the flag below.**

- **Agentic / LLM orchestration (growth):** the loop controller, the **analyzer agent** (the MOLLEO gap), explore/exploit, stopping rule, invalid-output fallback. Pitch: *"My agent analyzes each generation, forms a hypothesis about what's improving the objective, and conditions the next proposals on it — beating a strong classical baseline under a hard oracle budget."*
- **Eval / observability (load-bearing):** PMO sample-efficiency benchmarking vs. published baselines; Langfuse traces of every loop decision. Pitch: *"Every claim is backed by the benchmark the field uses, on a fixed oracle budget."*
- **Backend / system design (stated headline):** oracle-serving layer with **caching/memoization + budget enforcement** (oracle calls are the expensive, accounted resource), async batched scoring, reproducible-run infra, the agent runtime, the API.

**`[RE-DECIDE]` — the backend-headline tension.** The verified minimal project is **agentic + eval heavy and backend-thin**: CPU oracles, single-machine batch loop, an API wrapper. Genuine distributed-systems depth only appears when you serve *expensive* oracles (ADMET-AI / Vina / DiffDock on Modal), which is currently stretch. Two honest resolutions — pick one before spec:
1. **Accept the shift:** headline becomes agentic + eval; backend is solid-but-secondary (the serving/caching/budget layer is real, just not the star). Lowest risk; matches the de-risked MVP.
2. **Defend the headline:** pull Modal-served expensive oracles **forward into the MVP** so the serving platform, async batching, and caching carry real load. Higher scope/risk, but makes "backend = headline" true rather than aspirational.

The caching/memoization/budget-accounting framing ("designed for expensive oracles, demonstrated on cheap ones") is a legitimate middle path, but a senior reviewer will notice if the backend isn't actually exercised. Decide deliberately.

---

## 11. Week-one setup checklist (was "open questions"; mostly resolved → now concrete) `[CORRECTED]`

1. **Harness:** create the pinned conda env, install `mol_opt` + legacy PyTDC, reproduce one Graph-GA PMO result (proves the eval contract).
2. **Loop spike:** wire LangGraph + Langfuse around a trivial `LLM → TDC oracle → log` loop; measure valid-SMILES rate (>80% gate).
3. **Cost probe:** estimate LLM tokens to hit 10K oracle calls; confirm < ~$50/run or pick a fallback model.
4. **Differentiator confirm:** read MOLLEO source to verify the analyze step is genuinely absent (the narrative in §2/§10 depends on it).
5. **Backend re-decision (§10):** choose resolution 1 or 2 before writing the SPEC.

---

## 12. Settled-vs-open index (for doc-system)

**Locked & verified:** anchor (closed-loop optimization agent), loop shape (design→score→analyze→redesign), user/builder framing, eval-via-PMO/TDC, LLM-driven proposal+analysis, MOLLEO as reference arch, baselines (Graph GA / REINVENT / Genetic GFN ceiling), non-goals, stack defaults (PMO + PyTDC + LangGraph + Langfuse + Modal), recalibrated kill-switch, dependency-surface + cost risks.

**Open (decide at doc time):** data store; per-ADR alternative write-ups; final proposal-LLM choice.

**Re-decide before spec:** the backend-headline weighting (§10) — accept the agentic/eval shift, or pull expensive oracles forward to defend the backend headline.

**No remaining unverified `[judgment]` external claims** — all resolved against the verification report (companion artifact).
