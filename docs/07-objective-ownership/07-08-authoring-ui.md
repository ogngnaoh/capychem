# Slice 07-08 — objective-authoring UI + live (milestone closer)

**Goal:** Surface everything the backend now carries — compose an objective, bring seeds,
see quality/diversity/novelty, download manifest + lineage, watch a resilient cockpit —
so a chemist drives the whole tool from the UI. **Closes milestone 07.**

## Split (this session vs. fresh session)
The user chose to land the **backend wiring** now and build the **visual UI in a fresh,
screenshot-iterated session**. So:
- **Backend wiring — DONE this session** (committed as 07-08 prep):
  - Novelty `seed_pop` wiring: gen-0 canonical population stashed in `LoopState` at persist;
    threaded through `stop_check` + the 3 runner-fallback `build_summary` calls → real runs
    emit `novelty` in `summary_json` (resume path = None, best-effort).
  - Quality on top-K: `build_summary` attaches `molecule_quality` to each `top_k` entry;
    `TopMolecule.quality` schema + `api.ts` type.
  - Diversity/novelty on the snapshot: `RunSnapshot.diversity`/`novelty`; DB path reads
    `summary_json`, the runner overlays them onto the live snapshot at finalize (the handle
    is never evicted, so the live path shadows the DB path for completed runs).
- **UI — PENDING (fresh session).** See the kickoff in `handoff.md`.

## UI task checklist (fresh session)
- [ ] 1. **Objective builder** component: pick oracles (`GET /catalog` + descriptor presets)
      + weights + transforms + SMARTS/property constraints; live preview via
      `POST /objective/validate`; collapses to the single-task pick in benchmark mode; sends
      `objective_json`/`constraints_json` in `createRun`.
- [ ] 2. **Seed-import** component: paste/upload SMILES (SDF/CSV parse), show accepted/rejected
      (RDKit-validated at `/runs`). (07-02 shipped the single-field version.)
- [ ] 3. **Quality + diversity display**: quality badges on top-K tiles (`TopMolecule.quality`);
      diversity/novelty in the run summary (`RunSnapshot.diversity`/`novelty`).
- [ ] 4. **Manifest + export downloads** on run-detail: `GET /runs/{id}/manifest`,
      `/export.csv`, `/export.sdf`.
- [ ] 5. **Cockpit**: analyzer per-component reasoning (which objective term moved) + WS
      reconnect-with-backoff + "connection lost" + cold-start "waking the model ~30s" copy.
- [ ] 6. Tests: vitest (objective builder + import + quality display); **extend the axe gate**
      (`e2e/a11y.spec.ts`) to the new surfaces; keep AA green.

## Acceptance (full slice)
A chemist composes a 2-term objective + a constraint + pastes a seed list entirely from the
UI, sees the `exploratory` badge, launches; the cockpit announces per-component reasoning and
survives a dropped socket; top-K tiles show quality; the run exports CSV/SDF + a manifest.

## Notes
- Use the frontend-design skill + the shipped Anthropic warm-token system (cream+coral,
  Source Serif 4/Inter). Iterate with `/run` + screenshots.
- Honesty on every surface: mode badge; figure-canon never "21/23"; exploratory =
  "not benchmark-comparable".
