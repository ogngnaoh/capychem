# Slice 05.02 — Hi-fi on-token surfaces + hybrid launcher + Runs/Compare re-skin

**Status:** in-progress · **Phase:** 2 (of 3) · **Gate:** ⏸ CHECKPOINT 2 (visual)

## Goal

Take the CP1-approved low-fi structure to a **hi-fi, on-token** finish: both hero surfaces
(Overview + Workbench cockpit) and the hybrid launcher rendered to production visual quality on
the existing `globals.css` tokens, plus a re-skin of Runs/Compare into the same shell. Still
**prototype fidelity** (mock data, under `/proto/*`) — no live API/WS wiring yet (that's slice 03).

## Plan

- **Evolve, don't restart:** build on the `apps/web/app/proto/*` routes from slice 01. Keep the
  disposable ribbon + shell; raise the fidelity.
- **On-token discipline (binding):** existing tokens only — warm cream + coral; Source Serif 4 @400
  headings (letter-spacing −0.02em), Inter body, Geist Mono for SMILES. Coral restrained to primary
  action / live state / the "this run" chart series. Charts via `chart-1` + `muted-foreground` CSS
  vars (no hardcoded hex). No new tokens/visual language.
- **Surfaces:** Overview (hero, loop, rigor strip, catalog peek) · Workbench running + completed
  (per the frozen §8 grid: reasoning hero left / AUC co-primary right / vitals / molecules) ·
  Launcher (NL + catalog + editable mirror + FR-015 guardrail gallery + no-match refusal) ·
  re-skin proto Runs (dense scannable table + status filter + 2-row compare select) and Compare
  (overlaid AUC coral=A / chart-2=B + side-by-side top-K + per-run stats) to the shell.
- **Polish fixes carried from slice 01:** AUC y-axis tick formatting; card empty-space rhythm;
  molecule tiles (still placeholder motif — real RDKit SVG is slice 03).
- **Loop:** re-use the existing Builder (continuity with the low-fi); Builder inner-loops with the
  frontend-design skill + 1280px screenshots; a **fresh** Critic reviews each round vs spec §7 +
  binding constraints. Cap ~7.

## Tasks

- [ ] Hi-fi Overview on-token (hero typographic hierarchy, loop diagram, rigor strip w/ figure canon, catalog peek).
- [ ] Hi-fi Workbench running + completed on-token (frozen grid; vitals; reasoning hero; AUC panel w/ GA reference line + delta; molecule tiles; fix y-axis ticks).
- [ ] Hi-fi Launcher on-token (NL box, catalog, editable mirror, projected envelope, FR-015 guardrail gallery, no-match refusal).
- [ ] Re-skin proto Runs + Compare to the shell/tokens (dense table; overlaid AUC; side-by-side top-K).
- [ ] Persistent shell/nav hi-fi (Overview·Workbench·Runs·Compare, `aria-current`); dark-mode toggle wired (full `.dark` palette exists) — light **and** dark both legible.
- [ ] Verify every round: 1280px no horizontal scroll (screenshot), typecheck clean, on-token (no new tokens / hardcoded hex), honesty labels intact, coral restrained.
- [ ] Critic pass green → assemble CHECKPOINT-2 (visual) packet for operator approval before productionizing.

## Notes

- Still no backend: static mock only. The intent-resolution endpoint + RDKit-SVG + live wiring are all slice 03.
- Dark-mode + full WCAG-AA contrast becomes a first-class check here (deferred from slice 01).
- Re-skinned Runs/Compare stay in `/proto` this slice; slice 03 productionizes into the real `/runs`, `/compare` (or ports the finalized design onto the existing components).
- Frozen design decisions: see `01-decisions.md`.
