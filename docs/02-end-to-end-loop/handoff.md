# Handoff — 02-end-to-end-loop (slice 06 SHIPPED: LLM beats Graph-GA on jnk3)

## Completed this session

- **Slice 06 SHIPPED** — funded the run, fixed the proposer for the live DeepSeek API, ran the
  jnk3 LLM-vs-GA head-to-head, got the **week-7 kill-switch verdict: LLM BEATS Graph-GA**, robust
  across two seeds. Every score in-silico (PRD N6).
  - **Verdict** (`capychem-eval --task=jnk3 --budget=10000 --head-to-head`): seed 42 → LLM **0.853**
    vs GA 0.684 (+0.169); seed 7 → LLM **0.782** vs GA 0.573 (+0.209). Valid-SMILES 98–99% (gate
    >80% ✓). LLM hits a higher AUC in fewer unique calls (sample-efficiency thesis). Both controls
    beat the published ref (0.553). Total DeepSeek spend ≈ **$1.60**; wall ~11–18 min/run.
  - **4 proposer fixes** (prereqs surfaced the first time the funded `direct` backend ever returned
    a real completion): `094f345` v4-pro cost rates + 128-tok cap · `20ed4e8` **non-reasoning chat
    mode** (`thinking:disabled` — load-bearing; both v4 models reason by default → empty content →
    would silently collapse to GA-vs-GA) · `13bc0bf` transient-failure → GA-fallback resilience.
  - Docs: slice doc `docs/02-end-to-end-loop/06-beat-graph-ga-on-jnk3.md` (frozen); milestone +
    index flipped. Gate green: pytest **130**, mypy 31, ruff.

## Slice status across milestone

- 01, 03, 04, 05, **06** → shipped + frozen. **02 `plateau-stop-and-signal` → planned (dep-free,
  last remaining slice in m02).**
- Milestone-02 exit criteria: 1–5, 7, **8 met**; **6 (plateau FR-003) outstanding → slice 02.**

## Current state

- **Slice 06 merged to `main` (ff) @ `d5e6fb4`; feature branch deleted.** `main` is local-only —
  ahead of `origin/main` (UNPUSHED, by choice). Working tree clean apart from `.claude/` (untracked
  tooling) + the `~8 grandfathered ruff-format` files (see below).
- DeepSeek balance ~$2.37 (delayed billing; near-free tolerance). `.env.local`: `direct` backend,
  model `deepseek-v4-pro`, key valid.

## Next session start here

1. Start **slice 02 `plateau-stop-and-signal`** (FR-003: `stop_reason()` reads `plateau_window`, a
   `plateaued` status, WS signal + `LiveRun.tsx`) — the LAST remaining m02 slice. Completing it closes
   milestone 02 → advance to milestone 03 (analyzer, the differentiator).
2. The analyzer-vs-no-analyzer with/without comparison (m03) should reuse slice 06's head-to-head
   harness on jnk3 — this run is the "without-analyzer" control.

## Active concerns

- **G6 ±1% reproducibility:** harness/GA/metric are deterministic; the hosted LLM (temp 0.7) is not
  bit-reproducible. The two-seed beat shows robustness, not ±1% — documented honestly in the slice doc.
- **LLM chemical prior:** DeepSeek likely recalls known JNK3 scaffolds vs de-novo discovery — a
  legit in-silico win (N6 disclaims real-world efficacy); the analyzer (m03) turns recall into a loop.
- Headless eval path has **no $50 cost gate** (only product/API loop does); bounded by unique-call
  budget, not auto-halted. DeepSeek billing is delayed → balance is not a live guardrail.
- `ruff format .` still wants to reformat ~8 *grandfathered* files (env.py, trace.py, a few tests)
  untouched by any slice — cosmetic; commit a one-line `chore: ruff format` whenever convenient.

## Slice log

- 2026-06-28 — Slice 06 SHIPPED: LLM beats Graph-GA on jnk3 (AUC 0.853/0.782 vs 0.684/0.573 @ seeds
  42/7), 98–99% valid; 4 proposer fixes for the live DeepSeek API; week-7 kill-switch PASSED.
- 2026-06-27 — Slice 06 code complete + reviewed; verdict run paused for the cost re-decision.
- 2026-06-26 — Slices 05 + 01 shipped + merged.
