# Slice 03 — web-polish

> Milestone 04, Track A, slice 03. NFR demo-responsiveness / G3 / Exit criterion #4. Frontend-only;
> **visual + responsiveness pass**; **$0 eval** (screenshots against route-mocked fixtures — no runs).
> Build order `01 → 02 → 03`; consumes the shipped browse + compare + run-detail surface.

## Goal

The full operator surface — launch (`/`), browse (`/runs`), run-detail (`/runs/[id]`), compare
(`/compare`) — renders cleanly at **1280px with no horizontal scroll**, and the two Exit-criterion-4 views
(run-detail + compare) are visually consistent with each other. No new endpoint, loop, scoring, LLM/oracle
call, WS, or DB change.

## Plan

**Audit (new capture specs, `apps/web/e2e/`)** — reuse the proven route-mock + 1280px PNG pattern of
`runs-shot.spec.ts` / `compare-shot.spec.ts`:
- `launch-shot.spec.ts` — `/` makes no API call on load; navigate + 1280px screenshot (no mock needed).
- `run-detail-shot.spec.ts` — route-mock `GET /runs/5` with a **terminal** snapshot (status `exhausted` ⇒
  `LiveRun` takes the no-WS branch) carrying a **deliberately long SMILES** + hypotheses; 1280px PNG.
- Re-capture `/runs` and `/compare` from the existing specs to confirm no regression.

**Fixes (surgical):**
- `apps/web/app/runs/[id]/LiveRun.tsx`
  - Top-molecules SMILES cell: make it **wrap** so column width never tracks SMILES length —
    `whitespace-normal break-all` (the base `TableCell` carries `whitespace-nowrap`, so `break-all`
    alone is inert; the `whitespace-normal` override is load-bearing). Align the table to compare's
    `TopKCard`: `#` → `tabular-nums text-muted-foreground`, score → `tabular-nums text-right`.
  - AUC chart x-axis → numeric, matching compare: `type="number"`,
    `domain={["dataMin","dataMax"]}`, `allowDecimals={false}` (reads by oracle-call value, not ordinal).
  - `text-zinc-500` → `text-muted-foreground` (Stat label + `conn` indicator) — theme token, dark-mode-correct.
- `apps/web/app/compare/CompareView.tsx`
  - `TopKCard` SMILES cell: `break-all` → `whitespace-normal break-all` (make the existing wrap real).
  - Long run label (`#id · task`) in `RunSummary` / `TopKCard` titles: keep the badge/title row from
    overflowing — let the label wrap / not force a single line.
  - `Stat` label `text-zinc-500` → `text-muted-foreground`.
- `apps/web/app/runs/[id]/HypothesisSection.tsx` — `· latest` `text-zinc-500` → `text-muted-foreground`.

**Critic loop** — fresh-context Critic invoking `frontend-design` on the polished run-detail + compare
(the two Exit-#4 views), cap N=10, until APPROVED; apply blocking findings, recapture.

## Tasks

- [x] Write this slice doc (decisions pinned)
- [x] Add `launch-shot.spec.ts` + `run-detail-shot.spec.ts` (long-SMILES, terminal-status fixture)
- [x] Audit: capture all 4 routes at 1280px; confirm the actual horizontal-overflow culprits
      (run-detail clipped the Score column on a long SMILES; ordinal chart x-axis)
- [x] Fix `LiveRun.tsx`: SMILES wrap (`whitespace-normal break-all`) + table alignment + numeric
      x-axis + `isAnimationActive={false}` + token
- [x] Fix `CompareView.tsx`: real SMILES wrap (`whitespace-normal`) + token
- [x] Fix `HypothesisSection.tsx`: token
- [x] Recapture all 4 routes; verified no horizontal scroll at 1280px, Score column restored, full curve
- [x] Gates green: pytest 240 · mypy strict (`-p capychem -p capychem.api`) · ruff · web vitest 26 · tsc · eslint
- [x] Frontend-design critic loop on run-detail + compare: **APPROVED round 1, zero blocking**
- [x] Checkpoint with operator → "ship + merge, don't push"; shipped

## Notes

**Design choices (decided — per the handoff, don't agonize):**
1. **Long-SMILES = wrap, not truncate.** `whitespace-normal break-all` everywhere a SMILES renders
   (run-detail + compare top-K). Wrapping shows the full string (the scientist reads/copies it; truncation
   hides data) and caps column width regardless of length. The subtlety: compare's existing `break-all` is
   inert under the base cell's `whitespace-nowrap` — this slice makes the wrap actually fire and applies the
   same treatment to run-detail for consistency.
2. **Run-detail chart x-axis → numeric** (`type="number"`), matching compare so both AUC charts read by
   value. Recharts handles the single-point / live-streaming case (YAxis stays `[0,1]`); low risk.
3. **Responsiveness target = 1280px clean, no horizontal scroll** (the NFR/demo bar, Exit #4). Mobile /
   narrow breakpoints are **OUT** (PRD/SPEC N11 web-only; demo bar is 1280). Polishing for 1280, not phones.
4. **Token consistency:** the 4 stray `text-zinc-500` spots → `text-muted-foreground` (theme token,
   adapts to dark mode); everything else already uses the token.

**Decided non-goals (not built):**
- **No `mutation_strategy` badge on compare** (the slice-02 deferral) — `CompareRun` lacks the field, so a
  badge needs a backend schema + endpoint change, exceeding a $0 visual-only pass; strategy is already
  legible (runs id'd by `#id · task`; "No analyzer hypotheses (Graph-GA run)" empty-state). Stays deferred.
- No new endpoint / loop / scoring / LLM / oracle call / WS / DB change. No mobile responsive work.
- No new visual identity — stay on the established shadcn + Tailwind surface; consistency over novelty.
- No real-world efficacy claim (PRD N6, every score is an in-silico oracle score).

**m03 carried minors — not folded:** the 5 carried minors are backend test-coverage items (m03 T1/T3/T4);
this slice touches only frontend files, so folding them would mean editing unrelated backend tests
(violates surgical-changes). The pre-existing `LiveRun` GET→WS-subscribe gap self-heals and is out of scope.
Left deliberately for slice 04/05 or a backend-touching change.

**No new logic ⇒ no new unit test.** Every fix is a className/recharts-prop change (pure CSS/visual); the
existing vitest suite must stay green. The screenshots are the evidence for Exit #4.

**Critic non-blocking minors left (APPROVED round 1, deliberately not folded):**
1. Run-detail's `10000 / 10000` "Oracle calls" stat wraps to two lines in the narrow 4-up card. Forcing
   one line (`whitespace-nowrap`) reintroduces the card-overflow this slice fights; shrinking every stat's
   font to fit one outlier degrades the others. The wrap is graceful, the grid stays even — left as-is.
2. The terminal-run header shows the `exhausted` badge next to a muted `done` — but `done` is the
   WebSocket connection-state indicator (connecting/live/done), not a status duplicate. Meaningful +
   pre-existing → out of scope.
