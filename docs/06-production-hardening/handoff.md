# Handoff — milestone 06 production-hardening

## Completed this session
- Resolved spec §13 open decisions (OD-1 cheap patches · OD-2 per-candidate budget · OD-3 flat cost cap · OD-4 annotate-only-in-benchmark quality gate · OD-5 provenance must be added · OD-6 docking→Phase 2 · OD-7 Python-class oracle plugin first).
- Ran a verified read-only code map of all six Phase-1 subsystems (6-agent workflow, independently re-verified the load-bearing claims against source).
- Wrote the Phase-1 implementation plan: `docs/superpowers/plans/2026-07-03-capychem-production-v1.md` (splits Phase 1 into milestone 06 production-hardening + milestone 07 objective-ownership).
- Stood up `docs/06-production-hardening/` (this milestone + handoff); updated `docs/milestones.md` (06 ← active, 07 planned).

## Slice status across milestone
- 06-01 repo-hygiene-and-docs → shipped
- 06-02 ci-pipeline → shipped
- 06-03 a11y-remediation → planned (start here)
- 06-04 axe-ci-gate → planned
- 06-05 alembic-baseline → planned
- 06-06 reliability-patches → planned

## Current state
- Branch: `main` (clean except the untracked design spec + this session's new docs). No feature code changed yet.
- Nothing deployed/mid-flight. Engine is the shipped m05 build.
- Key verified facts: harness JSON has no version field (`score.py:102`); cost gate flat `$50` at `cost.py:16`; no LICENSE/`.github`/Alembic; `ALLOWED_ORIGINS` hardcoded `config.py:15`; a11y failures confirmed (coral `--primary` 3.57/3.28:1, `ring-ring/50`, no `aria-live`); seed-SMILES bug sinks at `graph.py:48-50`.

## Next session start here
Execute slice **06-03 a11y-remediation** (WCAG AA at 1280px). Verified failures to fix (with anchors): (1) primary-button contrast — `globals.css:58` light coral `--primary` oklch(.635 .112 46)=3.57:1, `:93` dark=3.28:1; darken toward the existing `active:bg-[#a9583e]` (≈5.06:1), keep hue 46, re-check live/analyze/chart usages. (2) focus ring — `button.tsx:7` `ring-ring/50`≈1.7:1 → full-opacity ring token ≥3:1. (3) no `aria-live` anywhere → visually-hidden polite region in `Cockpit.tsx`/`LiveRun.tsx` announcing generation-complete/status/hypothesis (NOT every candidate tick); `role="alert"` on error `<p>`s (LiveRun:72-77, RunsBrowse:139, CompareView:91). (4) swallowed fetches → inline error/empty state (Overview:22/25, Launcher:56, CompareView:39, AppShell:67). (5) skip-to-content + `id` on `<main>` (AppShell); per-route `metadata` titles (5 page.tsx); `aria-sort` (RunsBrowse:149-163); concise `MoleculeTile` alt (ui.tsx:39, drop raw SMILES). Then 06-04 wires the axe-core gate. Consider running the a11y (frontend) and 06-05/06-06 (backend) work as parallel worktree Builders since their file sets are disjoint.

## Active concerns
- **Mode-split coupling:** milestone 07's seed-import/objective/oracle features each set `mode=exploratory` and need the `Run.mode` column — so 07-01 (mode) must precede them and every schema change waits on 06-05 (Alembic). Do NOT ship seed-import in 06.
- **Figure canon:** every new doc/badge must state "21 comparable, 2 excluded" from `figure_canon`, never a naive `excluded_rows`-length read of the g1 JSON (which says "1"). Never "21/23".
- **Two budget impls:** `eval/runner.py` (dict) and `loop/graph.py` (set) must stay byte-identical for G6 — any reliability edit to the score node must not diverge them.
- **Resume + plateau:** `auc_curve` is not persisted mid-run — the resume path must *recompute* it by replaying generations, not reset, or FR-003 plateau mis-fires after restart.
- **Execution discipline (repo learning):** run build subagents via file-write handoff / synchronously; independently re-verify every self-reported check; orchestrator owns all doc writes; reuse existing agents, create none.
