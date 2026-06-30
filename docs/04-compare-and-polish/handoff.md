# Handoff — 04-compare-and-polish

## Completed this session

- **Slice 03 `web-polish` SHIPPED** (NFR demo-responsiveness / G3 / Exit criterion #4). Frontend-only
  visual + responsiveness pass; **$0 eval** (screenshots vs route-mocked fixtures, no runs). Flow: slice doc
  → 1280px audit → surgical fixes → gate-green → frontend-design critic (APPROVED round 1, zero blocking) →
  ship. ff-merged to `main` (not pushed — `main` ahead of `origin`).
  - *Audit (1280px):* launch + browse already clean. **Run-detail** clipped its top-K **Score column** off
    the right edge on a long SMILES (table scrolled internally under `whitespace-nowrap`), and used an
    ordinal AUC x-axis (inconsistent with compare). **Compare** clean but its `break-all` was inert under
    `whitespace-nowrap` (untested on a long SMILES).
  - *Fixes (surgical, 3 components):* SMILES cells → `whitespace-normal break-all` on both top-K tables
    (the `whitespace-normal` override is load-bearing). Run-detail table aligned to compare (# muted, Score
    right-aligned). Run-detail AUC chart → numeric x-axis (`type="number"`) + `isAnimationActive={false}`,
    matching compare so both charts read by oracle-call value. 4 stray `text-zinc-500` → `text-muted-foreground`
    (theme token, dark-mode-correct). No new endpoint/loop/scoring/LLM/WS/DB change.
  - *Capture harness:* added `e2e/launch-shot.spec.ts` + `e2e/run-detail-shot.spec.ts` (terminal-status,
    long-SMILES fixture) and a long SMILES into `compare-shot.spec.ts` to stress the wrap.
- Gates green: backend ruff · mypy (37) · pytest **240**; web vitest **26** · tsc · eslint.

- **Anthropic / claude.ai design re-skin SHIPPED** (out-of-band — user-requested via an agent-team, NOT a
  planned milestone-04 slice). Gated build→critic loop (Scout → Builder w/ `frontend-design` → Critic w/
  Playwright 1280px screenshots), **2 rounds, both PASS, zero blocking**; **$0**. Global warm-token overhaul
  in `app/globals.css` (cream `#faf9f5` canvas, coral `#cc785c` primary/ring, warm grays @ oklch hue ~83°,
  8px radius, the 5 chart tokens) + `layout.tsx` fonts (**Inter** body + **Source Serif 4** headings @ weight
  400, Geist Mono kept) across all 4 routes; serif `CardTitle`; coral+warm-blue (`#d97757`/`#6a9bcc`) chart
  pair; warm on-token plateau notice; coral button hover/active. **Zero off-token colors remain.** Slice-03
  responsiveness wins untouched. Storyboard spec: session scratchpad `design-tokens-spec.md` (not in repo).

## Slice status across milestone

- 01 `runs-list-and-browse` → **shipped** · 02 `compare-runs` → **shipped** · 03 `web-polish` → **shipped**
- 04 `g1-full-23-sweep` → **next** (Track B; deps met — Track-A-independent; before 05) ·
  05 `readme-and-langfuse-walkthrough` → planned (last)

## Current state

- Branch `main` — slice-03 code + e2e specs + these doc updates shipped in one commit, **ff-merged to main,
  NOT pushed** (origin synced at `b0d6202`; `main` now ahead). `docs/milestones.md` still marks `04 ← active`
  (correct — milestone not complete). This slice spent **$0**; the DeepSeek top-up remains reserved for
  slice 04's G1 sweep.

## Next session start here

- **EXECUTE slice 04 `g1-full-23-sweep`** (Track B, the milestone's only spend slice). Write the slice doc
  first, then: (1) **two mandatory pre-sweep harness guards** — median2 Graph-GA `crossover.py:142`
  `IndexError` (guard empty `RunReactants`) and the sitagliptin_mpo oracle NaN slipping past the measurement
  read (`math.isnan` guard; also a ~3-4× cost fix); (2) authoritative `capychem-eval --all` with-analyzer-LLM
  vs vanilla Graph-GA, budget=10000, seed=42, via the canonical `packages/core/capychem/eval` module →
  establish the **≥6/23** count (week-8 already has 7 trustworthy beats among 9; this completes the
  denominator). A null result (<6) is documented honestly, not hidden. **Never import the harness — subprocess
  + JSON only.** Confirm spend budget before invoking the full sweep.

## Active concerns

- **`_run_snapshot` cost-read seam** (detail + compare): the DB-path `cost.run_cost_total` read is
  load-bearing for FR-013 — keep it if a future slice touches the snapshot path.
- **Charts now unified:** run-detail + compare both use numeric x-axis + `isAnimationActive={false}`. Any new
  chart should match.
- **Slice-03 non-blocking minors left (critic-agreed):** run-detail `10000 / 10000` stat wraps to 2 lines in
  the narrow 4-up card (forcing nowrap reintroduces overflow — left); the terminal-run `done` next to the
  status badge is the WS connection indicator, not a duplicate.
- **Track B (slice 04) pre-sweep guards stay mandatory:** median2 `IndexError`; sitagliptin NaN.
- **Web surface is now Anthropic-themed** — slice 05's README/Langfuse screenshots will show the cream+coral+
  serif surface. Two redesign coverage nits (code-verified, not screenshot-verified): the warm plateau notice
  (no `plateaued` fixture renders it) and the browse `bg-accent` selected-row state (no row selected in fixture).

## Slice log

- 2026-06-30 — Milestone 04 kicked off and planned; DeepSeek topped up for the G1 full-23 sweep.
- 2026-06-30 — Slice 01 `runs-list-and-browse` SHIPPED (`main @ 5ff32c3`).
- 2026-06-30 — Slice 02 `compare-runs` SHIPPED (`main @ b0d6202`); cost-read fix on shared `_run_snapshot`.
- 2026-06-30 — Slice 03 `web-polish` SHIPPED: 1280px demo-responsiveness pass — SMILES wrap, unified numeric
  AUC x-axis, token consistency; Exit #4 MET. Critic APPROVED round 1. $0. ff-merged to main (not pushed).
- 2026-06-30 — **Anthropic/claude.ai design re-skin SHIPPED** (out-of-band, agent-team, 2 PASS rounds, $0):
  warm cream+coral token overhaul + Source Serif 4 / Inter across all 4 routes. ff-merged to main (not pushed).
