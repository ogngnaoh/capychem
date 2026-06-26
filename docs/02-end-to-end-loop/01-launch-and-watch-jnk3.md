# Slice 01 — launch-and-watch-jnk3

> Milestone 02 (`end-to-end-loop`). Status: **shipped 2026-06-26 — frozen**. Deps: none.
> Design: `docs/superpowers/specs/2026-06-26-launch-and-watch-jnk3-design.md`.
> Plan: `docs/superpowers/plans/2026-06-26-launch-and-watch-jnk3.md`.

## Goal

Make `jnk3` a launchable + watch-live target on the existing Graph-GA loop — the
harness scores it, the API accepts it, and a jnk3-targeted web form starts a run
and routes to its live view (Story 1 / FR-001 + Story 2 / FR-009; exit criterion 7).

## Plan

- **Harness** (`harness/pyproject.toml`, `harness/uv.lock`, `harness/capychem_harness/score.py`):
  pin `scikit-learn==1.2.2` + `numpy<2`, add `sklearn.ensemble.forest` /
  `sklearn.tree.tree` `sys.modules` shims so jnk3's legacy RandomForest pickle
  loads. rdkit stays `2026.03.2` (verified) ⇒ Graph-GA byte-identical. Gitignore
  `oracle/` (TDC model cache).
- **API** (`apps/api/capychem/api/schemas.py`): `task: Literal["qed", "jnk3"]`
  (default `"qed"`). `mutation_strategy` + `plateau_window` already accepted +
  threaded to `RunConfig`.
- **Web** (`apps/web/app/page.tsx`, `apps/web/lib/api.ts`, `apps/web/vitest.config.ts`):
  target jnk3, retitle, add a `plateau_window` field + a native `mutation_strategy`
  select; extend `CreateRunBody`; add the `@/` vitest alias.
- **Watch-live**: `LiveRun.tsx` unchanged (already renders the live surface);
  plateau status/signal is slice 02's — seam left clean.
- **Testing**: harness-gated jnk3 score (spread) · API task validation + config flow
  · Vitest form test · opt-in Playwright jnk3 smoke · in-session live acceptance.

## Tasks

- [x] Task 1 — Harness jnk3 fix (pins + shims + gitignore + jnk3 test + full-suite re-verify)
- [x] Task 2 — API task surface (`Literal["qed","jnk3"]`, FR-015 refusal, config-flow tests)
- [x] Task 3 — Web form targets jnk3 (`plateau_window` + `mutation_strategy` select, `api.ts`, vitest alias)
- [x] Task 4 — Playwright smoke targets jnk3 (opt-in)
- [x] Task 5 — Full gate + live launch→watch acceptance (pytest 113, web 9/9, live e2e passed)

## Notes

- **Verified pre-work:** sklearn `==1.2.2` is the newest keeping the 7-field tree
  dtype the jnk3 pickle needs (1.3.0 added `missing_go_to_left`); two shims needed,
  not one; rdkit co-resolves with numpy<2 (no Graph-GA drift); jnk3 gives a real
  score spread (kinase-like probe 0.51 vs ~0 for benzene) — not a degenerate unpickle.
- **Perf note (out of scope):** the harness spawns a fresh subprocess per score
  batch, each re-loading the ~10 MB jnk3 model (~10 s). Fine for this slice; a
  warm/persistent harness is a later concern (slice 06 / perf).
- **Deferred to slice 02:** plateau stop + live plateau signal — this slice only
  captures `plateau_window` as config and leaves the `LiveRun` seam clean.
- **Slice-06 BLOCKER untouched:** `summary_json.valid_smiles.rate` gate purity.
