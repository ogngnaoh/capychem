# Handoff — 00-walking-skeleton

## Completed this session

- **Slice 4 (`03-cloudify`) fully planned + reviewed — ready to implement (NOT shipped).**
  Brainstormed the approach (4 decisions via Q&A), wrote the design spec, implementation plan, and
  slice doc, then ran an adversarial reviewer subagent against the codebase and applied its fixes.
  **No production code changed this session — planning artifacts only.**
- Artifacts: `docs/superpowers/specs/2026-06-11-cloudify-design.md`,
  `docs/superpowers/plans/2026-06-11-cloudify.md`, `docs/00-walking-skeleton/03-cloudify.md`.
- **Decisions locked:** (1) Modal hosts oracle scoring only (Graph-GA proposer stays local);
  (2) env-selected backend `CAPYCHEM_ORACLE_BACKEND=local|modal`, scoring goes async (kills the
  event-loop block); (3) minimal real cost gate now (`RunCost` table + `$`-cap → `cost_capped`);
  (4) a deployed-Modal QED browser run closes the slice AND the milestone.
- **Reviewer caught + fixed in the plan:** Task 6 was written against a non-existent web reducer
  (real API is `applyEvent`/`RunSnapshot`); `cost_capped` missing from the live-view `TERMINAL` set;
  `import modal` in core needed a `modal.*` mypy override; worker image carried an unproven
  `rdkit.six` shim (score.py shims itself — dropped it); `aiosqlite` made an explicit dev dep.

## Slice status across milestone

- `00-foundation` → shipped (2026-05-30)
- `01-local-loop` → shipped (2026-06-11)
- `02-web-surface` → shipped (2026-06-11)
- `03-cloudify` → **planned; fully specced + reviewed; implementation not started**

## Current state

- Branch `main`. No code changed since slice 3 ship — the full green gate still holds.
- Slice-4 planning docs added this session. Modal account NOT yet provisioned.

## Next session start here

Execute `docs/superpowers/plans/2026-06-11-cloudify.md` via **superpowers:subagent-driven-development**,
Task 1 first (RunCost model + cost helpers). Tasks 1–4 + 6 are fully local-verifiable (no Modal).
Before Task 5: provision a Modal account + export `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET` (the API
needs the same token to call the worker). Task 5 Step 4's deployed browser QED run is the
milestone-closing gate.

## Active concerns

- **Modal API version-sensitivity** (plan flags): `image.add_local_dir(..., remote_path=)` and
  `fn.remote.aio(...)` are the two calls most likely to need adjustment vs the installed `modal`.
- **Cloud-run gate needs Modal** — slice 4 can be built + green locally, but the milestone stays
  open until the deployed QED run passes.
- Carried: sync harness *propose* still blocks briefly (acceptable); `Run.ended_at` unset;
  post-restart snapshots in-memory; Langfuse enabled-path trace unverified (no keys).

## Slice log

- 2026-06-11 — Slice 4 (`03-cloudify`) planned + reviewed (spec/plan/slice doc); ready to implement.
- 2026-06-11 — Slice 3 (`02-web-surface`) shipped.
- 2026-06-11 — Slice 2 (`01-local-loop`) shipped.
- 2026-05-30 — Slice 1 (`00-foundation`) shipped.
