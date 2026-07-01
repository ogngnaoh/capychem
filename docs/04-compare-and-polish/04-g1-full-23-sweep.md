# Slice 04 — g1-full-23-sweep

> Milestone 04 Track B — the milestone's **only spend slice** (real DeepSeek cost for the
> with-analyzer-LLM arm). Two mandatory pre-sweep harness guards (TDD), then the authoritative
> full-23 with-analyzer-LLM-vs-vanilla-Graph-GA sweep establishing the **G1 ≥6/23** count.
> Every score is an in-silico oracle score (PRD N6). A null result (<6/23) is documented
> honestly, not hidden.

## Goal

Establish the authoritative **G1 benchmark count** — how many of the 23 PMO tasks the
with-analyzer-LLM agent beats vanilla Graph-GA on, by AUC-of-top-10 under a 10,000 unique-oracle-call
budget — measured strictly via the canonical `packages/core/capychem/eval` module, with both known
harness anomalies guarded so all 23 tasks produce trustworthy rows. Render the G1 verdict (≥6 → goal
met; <6 → documented honestly). (Milestone Exit criterion #5; G1.)

## Plan

**Guard 1 — Graph-GA crossover empty-`RunReactants` `IndexError` (harness).**
`harness/capychem_harness/graph_ga/crossover.py`. The defect `rxn.RunReactants((fa, fb))[0]` raises
`IndexError` when the reaction yields no products. It appears at **two** sites — `crossover_non_ring`
(line ~142, the documented `median2` crash) and `crossover_ring` (line ~109, the identical latent
defect). `propose.py` has **no try/except** around `co.crossover()`, so an `IndexError` in *either*
crashes the whole propose subprocess for that generation → an `ok=False` (non-trustworthy) sweep row.
Guard both: capture the products, skip on empty. Surgical; vendored-file provenance comment updated to
note the minimal guard (no longer byte-verbatim).
- TDD: `harness/tests/test_crossover_guard.py` — a standalone assert-script (harness venv has **no
  pytest**; adding it would churn the pinned 3.10 lockfile). Monkeypatches `ReactionFromSmarts` to a
  fake reaction whose `RunReactants` returns `()`, drives `crossover_non_ring` with real `cut`-able
  parents, asserts it returns `None` (not `IndexError`). Run: `harness/.venv/bin/python
  harness/tests/test_crossover_guard.py`. **Never import the harness from modern code** — this script
  runs *under* the harness interpreter, the only legitimate way to exercise harness internals.

**Guard 2 — sitagliptin_mpo oracle NaN slipping past the measurement read (modern).**
`packages/core/capychem/eval/runner.py::run_reproduction.score_unique` — THE ingestion read path for
every sweep mode (reproduce / head_to_head / analyzer_verdict / week8 all funnel through
`run_reproduction`). The current guard `if r.valid and r.score is not None and …` lets a NaN score
into `mol_buffer` (NaN is not None). A NaN then poisons the PMO patience check (`cur_top - prev_top <
1e-3` is always False for NaN → patience never decrements → the loop runs to budget exhaustion: the
observed ~229-generation, ~3–4× sitagliptin blowup). Add a finiteness guard at ingestion so the NaN
is dropped → AUC stays clean AND patience terminates normally (the cost fix). Use `math.isfinite`
(subsumes the documented `isnan` case and also rejects ±inf; same surgical footprint). Guarding only
at the final measurement read would clean the number but NOT fix the cost — ingestion is the only
location that does both.
- TDD: extend `packages/core/tests/test_eval_runner.py` — (a) a NaN-scoring SMILES never enters
  `mol_buffer`; (b) an all-NaN-offspring run terminates on patience (`unique_calls < budget`,
  `generations` small) rather than running to budget exhaustion.

**G1 sweep (the spend).** `uv run capychem-eval --all --week8 --budget=10000 --seed=42` → `week8`
mode = `run_head_to_head(analyzer=True)` per task = with-analyzer-LLM vs vanilla Graph-GA, both
measured via canonical `top_auc`, with the guarded `week8_verdict` rendering **trustworthy_beats**
(beats whose LLM arm passed the valid-SMILES gate AND analyzer parse-rate floor). The G1 count =
trustworthy_beats out of 23. **Checkpoint with the operator before invoking** (it spends; DeepSeek
balance topped up 2026-06-30 for exactly this). Sanity-check one task on a small budget first.

## Tasks

- [x] Restore the accidentally-deleted `agent_docs/pmo-auc-and-baselines.md` (referenced by `metric.py:4`).
- [x] TDD Guard 1: `harness/tests/test_crossover_guard.py`; guarded both crossover sites (`6b4efb1`).
- [x] TDD Guard 2: NaN-ingestion + patience tests in `test_eval_runner.py`; `math.isfinite` guard (`6b4efb1`).
- [x] **Guard 3 (surfaced by the smoke): drd2 SVM-pickle shim** in `harness/score.py` + `test_drd2_oracle.py`
      (`00b03a6`). drd2's oracle was returning all-invalid → GA-arm crash; now scores correctly.
- [x] Gates green: ruff · mypy (37) · pytest (242, +2) · harness crossover (2) · harness drd2 (1).
- [x] Sanity checks (no spend): qed + sitagliptin graph_ga reproduce — guards behave.
- [x] **CHECKPOINT (spend):** operator chose smoke-first. 1-task DeepSeek probe (qed@500) healthy.
- [x] **Smoke: `--all --week8 --budget=2000 --seed=42`** (raw JSON `smoke-23-2k-seed42.json`, this folder):
      **22/22 evaluated tasks beat** (drd2 excluded — its oracle bug found+fixed here, not yet re-swept).
- [x] **Ran the authoritative 10k sweep** — `--all --week8 --budget=10000 --seed=42`, 22 tasks
      (sitagliptin_mpo pre-excluded), batched per-task under an operator $20 cap, metered live via the
      DeepSeek balance API. Raw per-task JSON in `g1-run/`; merged verdict `g1-full23-10k-seed42.json`.
- [x] **Investigated sitagliptin_mpo >1 AUC → oracle defect, excluded-for-cause.** `top_auc` cannot
      exceed 1 unless scores exceed 1; only sitagliptin does (1 of 23), so the metric is sound and the
      defect is task-local. Excluded (never run in the 10k sweep).
- [x] **Systematic baseline-repro check at verdict time caught a SECOND defect: valsartan_smarts.**
      GA control 0.757 vs published 0.000 (largest miss by 6×); the pinned-PyTDC oracle scores a pocket
      the canonical task doesn't. Excluded-for-cause (internal same-seed head-to-head still favored the
      LLM +0.103). The valid+parse guards miss both defects — a `|GA_control − published| > 0.15` gate does not.
- [x] **Rendered the G1 verdict — G1 MET decisively.** 21 trustworthy beats of 21 comparable tasks
      (bar 6); 2 of 23 excluded-for-cause; denominator 23. All 21 rows `ok=True`, guards healthy, none degraded.
- [x] **CHECKPOINT (merge):** operator reviewed the verdict + the 22→21 valsartan honesty catch and
      approved shipping the "21/21 comparable, 2 excluded" framing (`/ship-slice`).
- [x] Ship: froze this doc, flipped slice 04 → shipped + advanced slice 05 in milestone.md + handoff.md;
      dated log line; committed on the branch (merge to main + push are the operator's call).

## Progress & findings — session 1 (2026-06-30/07-01), branch `slice-04-g1-full-23-sweep`

- **Three harness fixes landed + TDD'd, gates green** (`6b4efb1` guards; `00b03a6` drd2). The two planned
  guards PLUS a third (drd2 SVM shim) the smoke surfaced.
- **2k smoke = decisive breadth signal:** 22/22 evaluated tasks beat vanilla Graph-GA with the analyzer,
  all valid-gates + parse-rates healthy. Standouts: mestranol +0.54, albuterol +0.38, troglitazone +0.35,
  celecoxib +0.30. Thin: qed +0.007, deco_hop +0.036, median2 +0.051.
- **Devil's-advocate review → verdict POLISH (run full 10k), ~85% confidence.** Decisive points, all
  repo-verified: (1) the slice Goal + Exit #5 require **budget=10000, all-23, trustworthy** — a 2k screen +
  9-task week-8 doesn't meet the written bar; (2) **sitagliptin's smoke row is out of range** (>1) → NOT
  trustworthy, the two-guard read misses it; (3) **drd2 never run through a sweep**; (4) **2k→10k is unsafe
  for thin margins** — troglitazone shrank +0.35@2k → +0.12@10k (week-8) as GA got more generations, so
  qed +0.007 etc. could flip. G1 pass/fail IS already settled (week-8: 7 trustworthy beats @10k ≥ 6); the
  full run is about a clean, unasterisked denominator, not about passing.
- **Cost:** week-8 was $10.08 for 9 tasks @10k (incl. sitagliptin's now-guarded blowup). Full-23 @10k ≈
  **$25–30**; DeepSeek-v4-pro $0.435/$0.87 per M in/out. Keep a safe balance so a mid-run $0 doesn't
  silently degrade the LLM arm to GA (slice-02 failure mode; guards catch it but the run is wasted).

## Notes / decisions (deviations from the literal handoff, all justified)

- **NaN guard in `runner.py`, not sweep/verdict/cli.** The milestone parenthetical named those three,
  but `score_unique` (runner) is the universal ingestion read every mode funnels through, and only
  ingestion-level guarding delivers the cost fix. One guard covers all modes.
- **`math.isfinite`, not `math.isnan`.** Strictly safer (NaN ∪ ±inf), zero added risk, same line.
- **Both crossover sites guarded** (142 non-ring = documented; 109 ring = identical latent defect).
  Either crashes the whole propose subprocess (no try/except in `propose.py`), so both threaten the
  "all 23 trustworthy" bar. If the critic prefers minimal scope, line 109 is trivially revertible.
- **Sweep mode is `--week8`** (with-analyzer-LLM vs Graph-GA + guarded verdict), not bare `--all`
  (which is `reproduce` = GA-only, not the G1 head-to-head).
- **Spend is the real risk vector, not dollars** (tolerance <$50 total; finishability + a trustworthy/
  null result are the risks — see memory eval-compute-budget). Checkpoint before the sweep; the NaN
  guard also caps sitagliptin's runaway cost.
- Open: the full sweep's wall-clock (DeepSeek latency + ~30s cold start × ~30 gens × 23 tasks) may be
  long; consider running in the background and monitoring. Week-8 already had 7 trustworthy beats among
  9 evaluated — this slice completes the denominator.

## Progress & findings — session 2 (2026-07-01): authoritative 10k run + G1 verdict

**G1 MET — decisively.** 21 trustworthy beats of 21 comparable PMO tasks (bar was ≥6); denominator 23,
2 excluded-for-cause. Every reproducible task beat the same-seed vanilla Graph-GA control; none degraded.
Authoritative verdict + excluded rows + diagnostics: `g1-full23-10k-seed42.json`.

- **Two excluded-for-cause (documented, not hidden):**
  - `sitagliptin_mpo` — PyTDC 0.3.6 oracle emits out-of-[0,1] scores for optimized molecules (AUC 1.75/2.26
    where the metric ceiling is 1.0). Task-local (only 1 of 23 exceeds 1.0, so `top_auc` is sound). Pre-excluded.
  - `valsartan_smarts` — caught at verdict time by a **systematic baseline-reproduction check**
    (`|GA_control − published| > 0.15`): GA control 0.757 vs published 0.000, the largest miss by 6×. The
    pinned oracle scores a molecule pocket the canonical PMO task doesn't. The internal same-seed head-to-head
    still favored the LLM (+0.103), but the row is non-comparable to the benchmark. This defect is invisible
    to the valid-SMILES + parse-rate guards (its scores are in-range); the baseline-repro gate is what caught it.
    The next-largest gaps — jnk3 (0.131, GA *higher* = a tougher control) and celecoxib (0.111, LLM won +0.344)
    — are within single-seed variance and do not undermine the result.
- **Honest margin framing (for the slice-05 README):** decisive (>0.1 AUC) on **9** tasks (troglitazone +0.563,
  mestranol +0.397, celecoxib +0.344, median1, perindopril, isomers_c9, thiothixene, albuterol, jnk3); thin /
  within single-seed noise (<0.03) on 4 (qed +0.005, deco_hop +0.009, zaleplon +0.018, drd2 +0.024). Truthful
  headline = **"beat or matched vanilla Graph-GA on all 21 reproducible PMO tasks (single seed, budget 10k),
  decisively on 9"** — crushes G1 without overclaiming SOTA (PROJECT.md thesis).
- **Cost: $18.94 total** (balance $25.79 → $6.85), **under the operator's $20 cap**. Metered per-task via the
  DeepSeek balance API between batched `--tasks` invocations (the CLI emits no dollar figure); a balance floor
  auto-stopped before the cap. drd2 confirmed cheap (~$0.11–0.44/task; the feared MPO blowups did not recur —
  guards held). Run resumed 4× across machine-sleep interruptions (per-task JSON banks incrementally → resume-safe).
- **Deviation from Exit #5's literal "all 23 trustworthy" sub-clause:** 21/23 are comparable+trustworthy; 2 have
  defective oracles in the pinned legacy env and are excluded-for-cause. The pre-sweep guards (crash/NaN) could
  not fix these — they are oracle-*semantic* defects, not crashes. The G1 count objective (≥6/23) is met at 21.
- **Artifacts:** `g1-full23-10k-seed42.json` (merged verdict), `g1-run/*.json` (raw per-task sweep_out),
  `g1-run/_progress.log` (metered-run record with the spend trail). Verdict methodology (guards + baseline-repro
  gate + exclusions) is described above; the merge tooling was a one-off orchestration wrapper (session scratchpad,
  not committed) around the canonical `capychem-eval`.
