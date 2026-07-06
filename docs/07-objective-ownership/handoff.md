# Handoff — milestone 07 objective-ownership

## Next session start here (07-08 UI — the milestone closer)
Milestone 07's **backend is 100% complete**, including 07-08's backend wiring (novelty
threading + quality/diversity/novelty on the run snapshot). The ONLY remaining work is the
**visual UI for 07-08**, to be built in this fresh, screenshot-iterated session. Branch off
`main` (branch-first), invoke the **frontend-design** skill, and build against the shipped
Anthropic warm-token system (cream+coral, Source Serif 4 / Inter). Iterate with `/run` +
screenshots. Deliverables (all in `apps/web`; the backend APIs already exist):

1. **Objective builder** — pick oracles (`GET /catalog` + the descriptor presets
   qed/sa_score/mw/clogp/tpsa) + weights + transforms (`identity`/`sigmoid`/`reverse_sigmoid`/
   `double_sigmoid`/`value_map`) + SMARTS-exclude/include + property-band constraints; live
   preview via `POST /objective/validate`; **collapses to the single-task pick in benchmark
   mode**. Sends `objective_json`/`constraints_json` in the `createRun` body (both already
   accepted + validated server-side; a non-null one ⇒ `exploratory`).
2. **Seed-import** — paste/upload SMILES (SDF/CSV parse), RDKit-validated at `/runs`; show
   accepted/rejected. (07-02 shipped the single space/comma field; this is the rich version.)
3. **Quality + diversity display** — badges on top-K tiles from `RunSnapshot.top_k[].quality`
   (SA/QED/Lipinski/Veber/PAINS/Brenk); `RunSnapshot.diversity`/`novelty` in the run summary.
4. **Manifest + export downloads** on run-detail — `GET /runs/{id}/manifest`, `/export.csv`,
   `/export.sdf` (all live).
5. **Cockpit** — analyzer per-component reasoning (which objective term moved) + WS
   reconnect-with-backoff + "connection lost" state + cold-start "waking the model ~30s" copy.
6. **Tests** — vitest for the objective builder + import + quality display; **extend the axe
   gate** (`apps/web/e2e/a11y.spec.ts`) to the new surfaces; keep WCAG-AA green.

**Honesty on every new surface:** mode badge; exploratory = "not benchmark-comparable";
figure-canon never "21/23".

## When 07-08 UI ships → MILESTONE 07 IS COMPLETE
In the ship commit: flip 07-08 → shipped in `milestone.md`; **flip `docs/milestones.md`**
(mark 07-objective-ownership shipped, next milestone `← active` or note "milestone 07
complete"); append a dated line to `log.md`; overwrite this handoff for the next milestone.
Per the milestone-boundary convention, the NEXT milestone starts in another fresh session.

## Current state
- **Milestone 07 backend COMPLETE** (01 mode-split · 02 seed · 03 pluggable-oracle · 04
  objective · 04b constraints · 05 quality+trust · 06 manifest · 07 export · **08 backend
  wiring**). Alembic head **`38f369ef45a6`**.
- 07-08 backend wiring shipped this session: gen-0 `seed_pop` stashed at persist + threaded
  through `stop_check`/runner fallbacks → `summary_json.novelty`; `build_summary` attaches
  `molecule_quality` to each `top_k` entry; `RunSnapshot.diversity`/`novelty` +
  `TopMolecule.quality` (runner overlays them onto the live snapshot at finalize since the
  handle is never evicted); `api.ts` types added.
- Gate all green: mypy (66) · ruff · **396** backend · web typecheck/ESLint · 40 vitest ·
  migration drift. `main` ahead of `origin/main` (unpushed) + m07-02..07 + the 07-08-wiring commit.

## Active concerns
- **UI-only remains** — no backend changes needed for 07-08 (all APIs exist). If a surface
  needs a field the snapshot lacks, prefer adding it to `RunSnapshot` over new endpoints.
- **Live vs. finalized snapshot:** quality/diversity/novelty are null WHILE a run is live
  (populated at finalize); the UI must handle nulls (show "computing…"/hide badges live).
- **Novelty is best-effort:** null on a resumed run (seed set not reconstructable). Tolerate null.
- Keep axe AA green (extend the gate); test basenames unique across the two roots.
