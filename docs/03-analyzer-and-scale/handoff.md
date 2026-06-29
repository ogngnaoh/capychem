# Handoff — 03-analyzer-and-scale

## Completed this session

- **Slice 06 `analyzer-conditioning` SHIPPED — the analyzer now ADDS value on jnk3.** Full cycle in one
  session: diagnosis → brainstorm → design spec → plan → subagent-driven execution → real verdict.
  - **Evidence-first paid off.** The slice-02 diagnosis *guessed* the hypotheses might be shallow; the
    Decision-Gate capture (budget-300 jnk3 `direct`, parse 1.0) **refuted that** — the analyzer's `focus`
    accurately IDs the winning naphthalene-amide scaffold. Real cause = **over-constraint** (long `avoid`
    list banning whole chemotype classes + narrow directive applied to all 70 offspring → diversity collapse).
  - **Fix = Approach 3A:** soften `focus` to optional inspiration, **DROP `avoid`** from the proposer prompt,
    condition only ~half the batch (`CONDITIONED_FRACTION=0.5`). Shared `strategy.py` → reaches the product
    loop too (both-paths parity free).
  - **Verdict (the deliverable) — WIN:** jnk3 @ seed 42, budget 10000: with **0.7641** > without **0.6744**,
    **diff +0.0897**, parse 1.0 (39/39), valid-rates 0.988/0.993 (both guards healthy). **Flips slice-02's
    −0.066.** Milestone **exit-criterion #5 now MET**; kill-switch did not need to fire.
- **SDD execution:** Tasks 1 (trace seam) → 2 (capture CLI) → 3A (soften/drop/fraction), each TDD +
  task-reviewed (Task 1 took 1 review fix: faithful `prompt_used`). Final whole-branch review (opus):
  **READY TO MERGE**. Gates: pytest 193, mypy 34 clean, ruff clean. Real spend this slice ≈ $1.1.

## Slice status across milestone

- 01 `analyzer-agent` → **shipped** (2026-06-28)
- 02 `analyzer-value-verdict` → **shipped** (2026-06-28) — trustworthy clean NULL (original conditioning)
- 06 `analyzer-conditioning` → **shipped** (2026-06-29) — WIN (+0.090 on jnk3; analyzer adds value)
- 03 `analyzer-live-surface` → planned (dep 01 ✓ — unblocked)
- 04 `twenty-three-task-surface` → planned (deps none — unblocked)
- 05 `week-8-sweep-and-gate` → planned (deps 01 ✓, 04, 06 ✓)

## Current state

- Slice 06 **ff-merged to `main`** (tip `c09841f`); slice branch deleted. **NOT pushed** — `origin/main` is
  **7 commits behind** (still at 25e5730). Push is the open decision for next session.
- Analyzer = **reasoning-OFF**, now with **3A conditioning** (soften + no `avoid` + half-batch) for the rest
  of the milestone. DeepSeek balance ≈ $3.1 (after the $4.27 top-up − ~$1.1 this slice).
- 2 non-blocking Minors logged (in `.superpowers/sdd/progress.md`): cli `fake_run` kwargs assertion; cli
  module-level `trace_to_dict` import. Optional cleanup.
- Stale leftover branch `slice-05-unique-call-budget-cost-ledger` exists locally (prior session) — unrelated.

## Next session start here

1. **Decide push:** `main` (c09841f) is 7 ahead of `origin/main`. Push if you want slice 06 on GitHub.
2. **Recommended next slice:** **04** (23-task surface) → **05** (Week-8 sweep) — the sweep is the
   authoritative bar and slice 06 cleared its dep. **Slice 03** (live surface) is independent. Strongly
   consider a **second seed (7) on jnk3** (~$1) to harden the single-seed slice-06 win before the sweep,
   given the backend non-determinism caveat below.

## Active concerns

- **Slice-06 win is single-seed + non-deterministic backend.** The `direct` backend's `seed` is best-effort:
  the without-arm drifted 0.743 (slice-02, 6/28) → 0.674 (today) at the SAME config (~0.07 noise ≈ the +0.090
  diff). Within-run controls day-drift and the sign flipped while the with-arm rose 0.678→0.764 — a coherent
  positive, but a SIGNAL not a noise-proof result. A 2nd seed (or the 23-task sweep) is the real confirmation.
- **`--analyzer-verdict` two-failure-mode caveat (carried):** always read BOTH `parse_rate_healthy` AND both
  `*_valid_rate` ≥ ~0.8 — a $0-balance mid-run silently degrades the LLM arm to Graph-GA with parse-rate still
  healthy. Confirm the balance covers the run first (query `https://api.deepseek.com/user/balance`).
- **Stale reasoning-ON references:** slice-01 design spec + frozen slice-01 doc still say "reasoning ON"
  (reversed in slice 02). Do not edit the frozen slice-01 doc.
- **Carried (deferred):** analyzer cost lands in `RunCost` one gen late (sub-cent); m02 live-UI plateau
  callout check; `plateauNotice` double-call hoist in `LiveRun.tsx` (Minor).

## Slice log

- 2026-06-28 — Slice 01 `analyzer-agent` SHIPPED (7 TDD tasks `015e7d1..2a84d46`).
- 2026-06-28 — **Slice 02 `analyzer-value-verdict` SHIPPED** (`ee86685..33da829`). Verdict: trustworthy
  clean NULL — analyzer does not add value on jnk3 @ seed 42 (0.678 vs 0.743) with the original conditioning.
- 2026-06-29 — **Slice 06 `analyzer-conditioning` SHIPPED** (`3fee112..6a4bda3` + docs). Evidence-first
  redesign: Decision-Gate capture proved the hypotheses are accurate but over-constraining → Approach 3A
  (soften focus, DROP `avoid`, half-batch). Verdict: **WIN** on jnk3 @ seed 42 (with 0.764 > without 0.674,
  **+0.090**; parse 1.0; valid 0.99/0.99). Exit-criterion #5 MET. Single-seed/non-determinism caveat noted.
