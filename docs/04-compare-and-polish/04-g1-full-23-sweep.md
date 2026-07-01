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
- [ ] **Run the authoritative `--all --week8 --budget=10000 --seed=42`** (drd2 now included); capture JSON.
- [ ] **Investigate sitagliptin_mpo >1 AUC** (smoke: llm=2.26, ga=1.75 — PMO scores must be [0,1]; the
      valid+parse two-guard read does NOT check score range). Decide: real PMO property, or a harness
      normalization bug → is sitagliptin's row trustworthy? Range-guard if needed.
- [ ] Render the G1 verdict: trustworthy_beats / 23; confirm all 23 `ok=True`; list any degraded/excluded.
- [ ] **CHECKPOINT (merge):** review verdict + diff with operator before shipping.
- [ ] Ship: freeze this doc, flip slice 04 → shipped + advance slice 05 in milestone.md + handoff.md,
      dated "Slice 04 shipped" log line, commit refs; merge to main (push on operator ask).

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
