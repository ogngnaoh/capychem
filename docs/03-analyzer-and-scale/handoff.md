# Handoff — 03-analyzer-and-scale

## Completed this session

- **Full pre-implementation stack for the analyzer-conditioning redesign (slice 06) — no code yet.**
  Diagnosis → brainstorm → design spec → implementation plan → slice doc → milestone registration.
  Decisions (via AskUserQuestion): direction = **redesign conditioning, chase AUC**; method =
  **evidence-first** (capture real hypotheses before designing the fix); **spec all three approaches**,
  evidence picks the fix at the Phase-2 gate.
- **Artifacts written (all uncommitted):**
  - Design spec: `docs/superpowers/specs/2026-06-29-analyzer-conditioning-redesign-design.md` (approved by user).
  - Implementation plan: `docs/superpowers/plans/2026-06-29-analyzer-conditioning-redesign.md` — Tasks 1–2
    (trace-capture seam + `--capture-analyzer-traces` CLI) in full bite-sized TDD; a Decision Gate;
    Tasks 3A/3B/3C (one runs, chosen by the gate); Phase-4 verify checklist. References verified against
    live code; **3B reuses `logic.is_plateau` (no duplicate); 3A extends `propose_llm_async`.**
  - Slice doc: `docs/03-analyzer-and-scale/06-analyzer-conditioning.md`; milestone.md updated (slice 06
    registered, build order `01 → {02∥03∥04} → 06 → 05`, slice 05 now deps 06).
- **Diagnosis recap (inferred from the code path, NOT proven — no hypothesis text was ever persisted):**
  hard directive applied to the whole batch every gen → diversity collapse + correlated bias; no headroom
  on jnk3; `avoid` is an asymmetric prune; reasoning-OFF reliable but possibly shallow. Phase 1 exists to
  confirm which dominates.
- **Prior session (context):** Slice 02 `analyzer-value-verdict` SHIPPED — trustworthy clean NULL on
  jnk3 @ seed 42 (with 0.678 < without 0.743). Commits `ee86685..33da829`. See slice log + frozen slice-02 doc.

## Slice status across milestone

- 01 `analyzer-agent` → **shipped** (2026-06-28)
- 02 `analyzer-value-verdict` → **shipped** (2026-06-28) — verdict: clean NULL (analyzer ≠ value on jnk3)
- 03 `analyzer-live-surface` → planned (dep 01 ✓ — unblocked)
- 04 `twenty-three-task-surface` → planned (deps none — unblocked)
- 05 `week-8-sweep-and-gate` → planned (deps 01 ✓, 04)

## Current state

- `main` is at `origin/main` (pushed 2026-06-28); **no code changes** this session — all pre-implementation
  docs. Working tree has **uncommitted docs**: design spec, implementation plan, slice-06 doc, milestone.md
  edit, this handoff. **Not yet committed** (awaiting the go to commit / branch). No slice branch created yet.
- Analyzer is **reasoning-OFF** for the rest of the milestone. DeepSeek balance ≈ $1 left — **must top up
  before the Phase-4 re-verify** (a full `--analyzer-verdict` run ≈ $1; Phase-1 capture ≈ $0.15).
- Implementation is **ready to execute** — the plan is reviewed and references are verified.

## Next session start here

1. **Execute slice 06** from `docs/superpowers/plans/2026-06-29-analyzer-conditioning-redesign.md`.
   First: commit the planning docs (and create the slice branch `slice/03-06-analyzer-conditioning` if
   isolating). Then run the plan via **`superpowers:subagent-driven-development`** (recommended — fresh
   subagent per task, review between) starting at **Task 1** (the `trace_sink` seam, full TDD on stub).
2. After Tasks 1–2: top up the DeepSeek balance, run the **budget-300 jnk3 `direct` capture** (the Decision
   Gate), read `/tmp/jnk3-traces.json`, classify Application/Timing/Content, and record the read in the
   slice doc. That picks Approach 3A (default) / 3B / 3C. Build the one fix, then Phase-4 `--analyzer-verdict`.
   - Slices **03** (live surface) and **04** (23-task surface) remain unblocked + independent if you'd
     rather build surface work in parallel; **05** (Week-8 sweep) waits until slice 06 improves the analyzer.

## Active concerns

- **The diagnosis is inferred, not proven.** Phase 1 (trace capture) exists precisely to confirm which
  mechanism dominates before committing to A/B/C. Do not skip it — it is the whole point of evidence-first.
- **No headroom risk.** jnk3 is the *hardest* task for the analyzer (LLM prior strongest). Even a good
  conditioning redesign may null on jnk3 specifically; a clean trace-backed null is still a valid result.
- **`--analyzer-verdict` two-failure-mode caveat (carried from slice 02):** read the verdict with BOTH
  `parse_rate_healthy` AND both `*_valid_rate` ≥ ~0.8 — a $0-balance mid-run silently degrades the LLM arm
  to Graph-GA while parse-rate stays healthy. Top up + confirm balance covers the run before Phase 4.
- **One seed only** (42, by scope). A second seed (7) would harden any result, ~$1 more.
- **Stale reasoning-ON references:** slice-01 design spec + frozen slice-01 doc still say "reasoning ON"
  (reversed in slice 02). Do not edit the frozen slice-01 doc; the reversal is recorded in the slice-02 doc.
- **Carried (deferred):** analyzer cost lands in `RunCost` one gen late (sub-cent); m02 live-UI plateau
  callout check; `plateauNotice` double-call hoist in `LiveRun.tsx` (Minor).

## Slice log

- 2026-06-28 — Slice 01 `analyzer-agent` SHIPPED (7 TDD tasks `015e7d1..2a84d46`).
- 2026-06-28 — **Slice 02 `analyzer-value-verdict` SHIPPED** (`ee86685..33da829`). Verdict: trustworthy
  clean NULL — analyzer does not add value on jnk3 @ seed 42 (0.678 vs 0.743). Reasoning-ON→OFF reversal
  (exit-criterion #4) after the instrumentation caught a 0/3 parse-rate. Kill-switch → pivot decision open.
- 2026-06-29 — **Diagnosis + brainstorm for the conditioning redesign** (no code). Direction = redesign
  conditioning / chase AUC; method = evidence-first; design spec written, all three approaches spec'd with
  an evidence-keyed decision tree.
- 2026-06-29 — **Slice 06 pre-implementation stack complete** (no code). Implementation plan + slice doc
  written, milestone.md registered (build order → `…→ 06 → 05`). Plan references verified against live
  code; 3B reuses `logic.is_plateau`. Stopped at ready-to-execute (session goal). Docs uncommitted.
