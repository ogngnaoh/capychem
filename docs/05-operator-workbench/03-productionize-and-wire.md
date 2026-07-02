# Slice 05.03 — Productionize + wire to live data (backend + frontend)

**Status:** in-progress · **Phase:** 3 (of 3) · **Gate:** ⏸ CHECKPOINT 3 (ship)

## Goal

Turn the CP2-approved hi-fi prototype into the **real** app: build the backend the design
needs (grounded intent resolution, RDKit 2D structures, missing read-fields), then productionize
`/proto/*` into the real routes wired to the live REST/WS, and verify end-to-end.

## Sub-slices

### 03a — Backend (`apps/api`, RDKit in the modern env)
Pinned contract (additive; do not break existing endpoints):
- **`POST /intent/resolve`** — body `{text: str, budget?: int, seed_smiles?: str}` → `IntentResolution`:
  `{ matched_task: str|null, confidence: "high"|"medium"|"low"|null, closest_task: str|null,
     rationale: str, resolved_plan: {task, budget, plateau_window, mutation_strategy, seed_smiles?}|null,
     refusals: [{field: "objective"|"budget"|"seed_smiles", reason: str}], cost_usd: float }`.
  Grounded to the 23 PMO tasks ONLY (never invents an oracle). Deterministic keyword/alias/fuzzy
  matcher is the default backend; an LLM path is used only if an LLM is configured (env), else skipped.
  Guardrails (FR-015): no match → `matched_task=null` + `closest_task` + a "no benchmark exists" rationale;
  invalid `seed_smiles` (RDKit parse) → refusal naming the field + why; non-positive/oversized budget →
  refusal. Cost-tracked (0.0 deterministic; real if LLM used).
- **`GET /molecule/svg?smiles=<smiles>&w=&h=`** — RDKit `rdMolDraw2D.MolDraw2DSVG` render; validates SMILES
  (400 on invalid); returns `image/svg+xml`; cacheable (ETag/Cache-Control on canonical SMILES). On-token:
  neutral stroke that reads in light+dark (SVG uses `currentColor` or a token-driven color).
- **Surface missing read-fields on `RunSnapshot`** (nullable, backward-compatible): `valid_smiles_rate: float|null`
  (from `summary_json.valid_smiles.rate`), `graph_ga_baseline: float|null` (per-task final GA AUC, loaded from
  `docs/04-compare-and-polish/g1-full23-10k-seed42.json` as a static lookup asset baked into the API),
  `cost` split if cheap (`llm_cost_usd`/`oracle_cost_usd` from `RunCost`) else keep scalar.
- Update `apps/web/lib/api.ts` types to match. Tests (pytest) for resolver grounding/guardrails + svg + fields.
- Constraints: mypy strict on new code (`uv run mypy -p capychem -p capychem.api`); never invent an oracle; N6 honesty.

### 03b — Frontend productionize (`apps/web`)
- Port the proto components into real components; replace/upgrade the real routes `/`, `/runs`, `/runs/[id]`,
  `/compare` with the hi-fi design wired to live REST/WS + `/intent/resolve` + `/molecule/svg`.
- Molecule tiles → real 2D SVG. Launcher → real resolve + launch. Cockpit → live snapshot + WS + new fields
  (valid-SMILES rate, GA baseline reference line + delta, cost). Keep the dark-mode toggle (in the shell now).
- Update the existing `*.test.tsx`; remove the `/proto` scaffold + `proto-shot.spec.ts` once the real routes verify.

### 03c — Verify (both)
- `uv run mypy -p capychem -p capychem.api`, `uv run pytest`, `uv run ruff check`; `pnpm --filter web typecheck`,
  `lint`, `test`. 1280px screenshots of **running / completed / empty** on the REAL routes, light+dark, no h-scroll.
  a11y (keyboard, status-not-color-only, reduced-motion). → ⏸ Checkpoint 3 (ship).

## Notes / risks
- No LLM env here → resolver ships deterministic-with-LLM-seam (still grounded + guardrailed). Launching a *new*
  run needs the loop/Modal; the read surfaces (runs list, detail, compare) wire against the ~290 existing Postgres
  runs, which also cover the running/completed screenshot states.
- Productionizing replaces working `LiveRun`/`RunsBrowse`/`CompareView` + tests — update tests alongside; keep the
  existing REST/WS contract intact (WS still emits generation.complete/analyzer.hypothesis/run.complete/ping).
- Reviewer run **synchronously** for a real report. Frozen design decisions: `01-decisions.md`.
