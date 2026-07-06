# Handoff — milestone 07 objective-ownership

## Next session start here
Branch off `main` (branch-first), then execute slice **07-08 objective-authoring UI +
live** — the LAST slice; it closes the milestone. Surface everything the backend now
carries. Scope (frontend + one small backend wiring):
1. **Objective builder** component (`apps/web`): pick oracles + weights + transforms +
   SMARTS/property constraints; live preview via `POST /objective/validate`; collapses to
   the single-task pick in benchmark mode. Sends `objective_json` / `constraints_json` in
   the `createRun` body.
2. **Seed-import** component: paste/upload SMILES (SDF/CSV parse optional), RDKit-validate
   at the `/runs` boundary, show accepted/rejected. (The single-field version shipped in
   07-02; this is the richer UI.)
3. **Quality + diversity display**: quality badges on top-K tiles (SA/QED/Lipinski/PAINS
   from `Candidate.quality_json`), diversity/novelty in the run summary. Needs the snapshot
   to expose quality — add `quality`/`diversity`/`novelty` to `RunSnapshot` + the run-detail
   read (small backend add).
4. **Novelty seed_pop wiring** (deferred from 07-05): stash the canonical gen-0 population
   in `LoopState` at gen 0; pass `seed_pop` through the `stop_check` + runner-fallback
   `build_summary` calls so real runs surface `novelty` (diversity already surfaces).
5. **Manifest + export download buttons** on run-detail (`GET /runs/{id}/manifest`,
   `/export.csv`, `/export.sdf`).
6. **Cockpit**: analyzer per-component reasoning (which objective term moved) + WS
   reconnect-with-backoff + "connection lost" + cold-start "waking the model ~30s" copy.
7. Tests: vitest for the objective builder + import + quality display; **extend the axe
   gate** (`apps/web/e2e/a11y.spec.ts`) to the new surfaces (keep AA green).

Use the frontend-design skill + the shipped Anthropic warm-token design system (cream+coral,
Source Serif 4/Inter). Iterate with `/run` + screenshots.

## When 07-08 ships → milestone 07 is COMPLETE
Land in the ship commit: flip 07-08 in `milestone.md`; then **flip `docs/milestones.md`**
(08-objective-ownership → shipped, next milestone → active or note "milestone 07 complete");
overwrite this handoff for milestone 08; per the milestone-boundary convention, the NEXT
milestone's build starts in a FRESH session.

## Current state
- Slice **07-07 shipped** (merged to `main`): lineage export. `GET /runs/{id}/export.csv`
  (per-candidate lineage + quality + hypothesis-at-birth columns) + `GET /runs/{id}/export.sdf`
  (RDKit round-trips it — props preserved; manifest git-SHA/PyTDC-pin embedded). `_lineage_rows`
  in `routes_runs.py` (Candidate⋈Generation, hypothesis-at-birth = hyp after gen g-1).
- **Backend is objective-ownership COMPLETE**: mode split (01) · seed plumbing (02) ·
  pluggable oracle (03) · composed objective (04) · constraints (04b) · quality+trust (05) ·
  manifest (06) · export (07). Alembic head **`38f369ef45a6`**. Only the UI (08) remains.
- Gate all green: mypy (66 files) · ruff · **394** backend (+3) · migration drift · web untouched.
- `main` ahead of `origin/main` (unpushed) + m07-02..07 commits.

## Active concerns
- **07-08 is the milestone closer** — it also does the deferred novelty seed_pop wiring +
  exposes quality/diversity in the snapshot (small backend add). Keep benchmark surfaces
  honest (mode badge everywhere; figure-canon never "21/23"; exploratory = "not
  benchmark-comparable"). Keep axe AA green (extend the gate to new surfaces).
- **Snapshot doesn't expose quality yet** — top-K tiles need `Candidate.quality_json`
  surfaced through `RunSnapshot.top_k` (add per-molecule quality) or a sibling field.
- Backend export/manifest are best-effort/nullable — the UI must tolerate nulls.
- Test basenames unique across the two roots; `.gitignore` `oracle/` root-anchored;
  new Alembic revisions chain from `38f369ef45a6`.
