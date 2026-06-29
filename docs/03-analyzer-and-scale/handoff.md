# Handoff — 03-analyzer-and-scale

## Completed this session

- **Slice 05 `week-8-sweep-and-gate` SHIPPED** (the milestone headline). Branch
  `slice-05-week8-sweep-and-gate`, commits `d3da81d` (spec) → `2a30fb6` (plan+slice doc) →
  `9c2f9ad`/`f5dadd3`/`3ec9899`/`c2b0d51`/`9ff10c4`/`0f6328b` (T1–T5 + lint) → verdict + ship docs.
  Built the **with-analyzer-LLM vs vanilla-Graph-GA** comparator (Approach A): `run_head_to_head(analyzer=True)`
  + analyzer-health on `BeatVerdict`, `week8` sweep mode, `week8_verdict` guarded reader, `capychem-eval
  --week8 --tasks`; cost-gate test proving the analyzer term is in the gated total. All TDD on the stub.
- **Week-8 verdict: bar CLEARED — 7 trustworthy beats → on track, NO pivot.** 9-task high-headroom
  subset @ budget=10000, seed=42, both `direct` backends, wall 139 min. **7/7 cleanly-measured tasks beat**
  their own same-seed Graph-GA control (jnk3 +0.083, median1 +0.122, zaleplon +0.026, troglitazone +0.117,
  perindopril +0.085, scaffold_hop +0.093, thiothixene +0.402); all guards healthy. Raw JSON committed at
  `docs/03-analyzer-and-scale/week8-sweep-seed42.json`.
- Gates green: **216 pytest**, mypy clean (36), ruff clean (no web touched).

## Slice status across milestone

- 01 `analyzer-agent` → shipped (2026-06-28)
- 02 `analyzer-value-verdict` → shipped (2026-06-28) — trustworthy clean NULL (original conditioning)
- 06 `analyzer-conditioning` → shipped (2026-06-29) — WIN, replicated seeds 42 (+0.090) & 7 (+0.108)
- 04 `twenty-three-task-surface` → shipped (2026-06-29) — registry + baselines + schema/UI + `--all`
- 05 `week-8-sweep-and-gate` → **shipped (2026-06-29)** — Week-8 bar CLEARED, 7 trustworthy beats
- 03 `analyzer-live-surface` → planned (dep 01 ✓ — the ONLY remaining slice; NO eval cost)

## Current state

- Branch `slice-05-week8-sweep-and-gate` ff-merged to `main` (local). **NOT pushed.** `main` is now ~18
  commits ahead of `origin/main` (slices 04 + 05 + earlier).
- DeepSeek balance ≈ **$2.91** (was $12.99; slice-05 sweep spent **$10.08**). Analyzer = reasoning-OFF + 3A.
- **Cost calibration:** real per-task cost at budget=10000 is **~$1.2/task** (MPO/median tasks run many
  generations before patience-stop — e.g. sitagliptin = 229 gens — vs jnk3's handful). A full-23 sweep ≈
  **$25–30**, not the earlier $15–23 estimate. Budget m04's G1 ≥6/23 push accordingly.

## Next session start here

- **Slice 03 `analyzer-live-surface`** — the last remaining milestone-03 slice (NO eval cost). WS
  `analyzer.hypothesis` event + watch-live latest-hypothesis panel + run-detail full hypothesis sequence
  (FR-009/FR-011, Story 2/3). Dep 01 ✓. Shipping it COMPLETES milestone 03 → then milestone 04.

## Active concerns

- **Two legacy-harness anomalies surfaced by the real sweep (follow-ups, NOT slice-05 bugs):**
  (1) median2 Graph-GA arm crashed — `IndexError` in `harness/.../graph_ga/crossover.py:142`
  (`rxn.RunReactants((fa,fb))[0]` on empty result; guard the empty case). (2) sitagliptin_mpo oracle
  returned **NaN scores** → NaN AUC; the two-guard read (valid+parse) does NOT flag a NaN AUC (slips
  through as "guards ok, non-beat" — conservative, never inflates the count). Future hardening: add a
  `math.isnan` measurement guard to `week8_verdict`.
- A subset clears ≥3 cleanly but cannot cleanly *pivot*; the full-23 count (G1 ≥6/23) is milestone 04.
- Frozen docs (do NOT edit): slice-01, -02, -04, -06, **-05** docs + their specs/plans.

## Slice log

- 2026-06-28 — Slice 01 `analyzer-agent` SHIPPED (`015e7d1..2a84d46`).
- 2026-06-28 — Slice 02 `analyzer-value-verdict` SHIPPED (`ee86685..33da829`). Trustworthy clean NULL.
- 2026-06-29 — Slice 06 `analyzer-conditioning` SHIPPED. WIN +0.090; hardened seed-7 +0.108. Exit #5 MET.
- 2026-06-29 — Slice 04 `twenty-three-task-surface` SHIPPED (`bd177b1..82a0f2b`). Exit #6 MET. No eval cost.
- 2026-06-29 — **Slice 05 `week-8-sweep-and-gate` SHIPPED.** Week-8 bar CLEARED (7 trustworthy beats /
  9-task subset). Exit #8 + #9 + #10 MET. Spend $10.08. Kill-switch did not fire.
