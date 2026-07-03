# Slice 06-03 — accessibility remediation (WCAG AA @ 1280px)

**Status:** shipped (frozen)

## Goal
Bring the operator workbench to WCAG AA at the 1280px target — real, verified fixes (axe-core green), preserving the cream+coral identity.

## What shipped
- **Contrast tokens (`globals.css`):** darkened `--primary` coral to `oklch(0.555 0.112 46)` (light, white-text 4.96:1) / `oklch(0.565 0.120 46)` (dark, 4.78:1) — same hue 46, identity preserved; `--ring`/`--sidebar-*` follow. Bumped dark `--muted-foreground` `0.580 → 0.630` (4.43:1 → ~5.5:1). Global focus `outline-ring/50 → outline-ring`.
- **Focus rings:** `button.tsx`/`badge.tsx`/`input.tsx` `ring-ring/50 → ring-ring` (full opacity, ≥3:1); button active-state `#a9583e → color-mix(--primary, #000 14%)` (theme-aware, darker-than-base).
- **Small coral text → foreground:** coral can't be both a white-text button bg AND small body text in dark mode, so small `text-primary` on tinted/dark surfaces (hypothesis chips, "differentiator"/"beating baseline"/focus/avoid chips, LoopDiagram + StatusChip labels, Overview emphasis) → `text-foreground`, keeping the `bg-primary/…` tint + `ring-primary/…` for identity. Coral kept on buttons, large headings (≥24px), chart-1, live dots, borders.
- **Screen reader:** visually-hidden `aria-live="polite"` region in `Cockpit` announcing milestones only (generation complete / status change / new hypothesis — never per-candidate ticks); `role="alert"` on async error messages (LiveRun, Cockpit stopErr, RunsBrowse, CompareView).
- **Surfaced swallowed fetches:** Overview (catalog+runs), Launcher (catalog), CompareView (runs selector), AppShell (runs) now show an inline message instead of `.catch(()=>{})`.
- **Structure:** skip-to-content link + `id="main-content"` on `<main>` (AppShell); per-route `metadata` titles on all 5 routes; `aria-sort` on RunsBrowse sortable headers; `<dl>`/`<dt>`/`<dd>` structure on the stat grids (Overview Figure, Compare Stat); `tabIndex={0}` + `aria-label` on the scrollable "Earlier hypotheses" region; concise `MoleculeTile` alt (`2D structure of molecule #N`, no raw SMILES).

## Acceptance — met (independently verified)
- **axe-core: 10/10 green** (5 routes × light+dark, zero serious/critical) — re-run independently, not just the Builder's claim.
- typecheck + lint + vitest (30) all clean.
- Visual check (light + dark run-detail screenshots): coral identity intact, chips legible, no design regression.
- Root causes were pre-existing (muted-foreground 4.43, coral-on-tint, dl, scrollable-region); the coral darkening *improved* chip contrast rather than causing it.

## Notes
- Contrast values were computed (OKLCH→sRGB→WCAG) not guessed; script in scratch.
- Stat tiles use `<dd>` (value) before `<dt>` (label) to match the value-prominent visual; axe's `only-dlitems` is order-independent. Semantically minor; accepted.
- The aria-live effect carries a scoped `set-state-in-effect` eslint-disable (syncing SR text to WS-driven snapshot deltas — no render-time "what changed" signal).
