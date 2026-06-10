# Handoff — 00-walking-skeleton

## Completed this session

- **Shipped slice 2 (`01-local-loop`)** via subagent-driven development — 16 tasks, each with a
  fresh implementer + spec-compliance review + code-quality review. 18 commits, `2bfcbc1..dfd5460`
  (planning artifacts: `a7ac849`; ship-docs commit follows this handoff).
- End-to-end loop runs locally: `capychem-run --task qed --budget <n> --seed 42` →
  propose (Graph-GA via harness bridge) → validate (RDKit) → score → persist (Postgres) → stop.
- Full green gate: **22 pytest pass**, mypy strict clean (12 files), ruff check + format clean,
  `scripts/smoke.sh` **9/9**.
- Two review catches worth remembering (now fixed/decided):
  - `loop/trace.py` `span()` masked with-body exceptions on the enabled path (second `yield` →
    `RuntimeError`); fixed + regression test added (`73f02eb`).
  - rdkit 2026.3 `rdkit-stubs` has a broken `.pyi` that halts mypy → scoped `rdkit.*` mypy
    override (`3af42f8`).

## Slice status across milestone

- `00-foundation` → shipped (2026-05-30)
- `01-local-loop` → **shipped (2026-06-11)**
- `02-web-surface` → planned (next)
- `03-cloudify` → planned

## Current state

- Branch `main`. Slice-2 code merged. Postgres + Langfuse containers up via
  `docker compose -f infra/compose.yml up -d` (+ `infra/langfuse-compose.yml`).
- `01-local-loop.md` slice doc is frozen. The loop is CLI-only (no API/WS/UI yet).
- The slice-3 design spec + implementation plan are drafted under `docs/superpowers/` and have
  passed an independent subagent review (see "Next session start here").

## Next session start here

Execute the **slice 3 (`02-web-surface`)** implementation plan at
`docs/superpowers/plans/<date>-web-surface.md` (design spec:
`docs/superpowers/specs/<date>-web-surface-design.md`) via
**superpowers:subagent-driven-development**. It grafts the committed in-process LangGraph loop
behind a FastAPI REST + WebSocket surface with a minimal Next.js launch + watch-live view on QED.
First action = plan Task 1.

## Active concerns

- **Langfuse enabled-path trace is unverified.** The no-op path (no keys) is CI-covered; the
  nested run→generation→node trace against a live Langfuse has NOT been manually checked (no
  `LANGFUSE_*` keys set this session). Set keys + run once when convenient (slice-2 design exit
  criterion, deferred).
- **`summary.auc_curve` is the running top-10 mean, NOT the canonical PMO AUC** — do not cite it as
  the G1 number; the authoritative AUC lives in `packages/core/eval` (later milestone).
- **Plateau (FR-003) is configured but not enforced.** Loop stops on budget / max-generations /
  zero-progress only. Plateau enforcement is deferred.
- **Slice 2 vendored only the two Jensen operators (no PyTorch)** — full `mol_opt` + `BaseOptimizer`
  baseline reproduction remains in milestone 01, not here.
- langgraph pin floor is loose (`>=0.2`, resolves to 1.2.x); builder generics are `[Any,…]`.
  Consider tightening to `>=1` when next touching loop deps.

## Slice log

- 2026-06-11 — Slice 2 (`01-local-loop`) shipped.
- 2026-05-30 — Slice 1 (`00-foundation`) shipped.
