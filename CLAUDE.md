# CLAUDE.md

CapyChem is an autonomous closed-loop molecular optimization agent. Start every session by loading the pointers below.

## Pointers
- @PRD.md
- @SPEC.md
- @PROJECT.md
- @docs/milestones.md — milestone index; the one marked `← active` is current.
- Active milestone: load `docs/<NN>-<name>/milestone.md` and `docs/<NN>-<name>/handoff.md` per `~/.claude/CLAUDE.md`. Synthesize those files when work on a milestone starts; do not pre-create.

**Build strategy: walking skeleton first.** Milestone `00-walking-skeleton` ships a thin end-to-end slice (1 PMO task, no analyzer, minimal UI) BEFORE the SPEC §9 phases dig in. Front-load integration risk; rigor follows.

## Commands

Install:
- `uv sync` — modern Python deps (root workspace: packages/core + apps/api)
- `uv sync --project harness` — isolated harness env (Python 3.10, PyTDC 0.3.6); separate venv, never a workspace member
- `pnpm install` — Node deps (root + apps/web)

Dev:
- `pnpm --filter web dev` — Next.js frontend on :3000
- `uv run uvicorn capychem.api.main:app --reload` — FastAPI backend on :8000
- `modal serve apps/worker/app.py` — Modal worker (LLM endpoint + oracle pool) in dev mode
- `docker compose -f infra/langfuse-compose.yml up -d` — local Langfuse

Build:
- `pnpm --filter web build`
- `uv build`

Test all:
- `uv run pytest`
- `pnpm --filter web test`

Test single:
- `uv run pytest packages/core/tests/test_loop_fallback.py::test_fallback_backfills_gap_for_llm -x`
- `pnpm --filter web test -- --runTestsByPath app/runs/[id]/page.test.tsx`

Typecheck:
- `uv run mypy -p capychem -p capychem.api` — strict; `capychem` is a PEP 420 namespace split across packages/core + apps/api, and mypy's `-p capychem` only resolves the FIRST `mypy_path` root (packages/core), so apps/api needs the explicit second `-p capychem.api`
- `pnpm --filter web typecheck`

Lint:
- `uv run ruff check .`
- `pnpm --filter web lint`

Format:
- `uv run ruff format .`
- `pnpm --filter web format`

Eval:
- `uv run capychem-eval --task=qed --budget=10000 --seed=42` — single PMO task
- `uv run capychem-eval --all --budget=10000` — full 23-task sweep (cost-bounded; confirm before invoking)

Legacy harness (isolated uv env, Python 3.10):
- `harness/.venv/bin/python harness/capychem_harness/score.py` — scores SMILES against a PyTDC oracle (reads JSON on stdin). Reproducing a Graph-GA baseline via `mol_opt` lands in milestone 01. Never `import` from harness; always shell out.

## Stack

- Python 3.12 (modern stack, pinned via `.python-version`); Python 3.10 (legacy harness env only)
- Node 22 LTS
- Next.js 16 (App Router) + React 19 + TypeScript 5 + Tailwind + shadcn/ui
- FastAPI 0.115+
- LangGraph (current)
- Postgres 16 (managed: Neon or Supabase — pick at infra-setup)
- Modal (LLM endpoint + oracle worker pool)
- DeepSeek-v4-pro (proposer and analyzer; same model)
- Langfuse self-hosted via Docker Compose
- RDKit (current)
- PyTDC 0.3.6 in `harness/` only (pinned legacy)
- uv + ruff + pytest + mypy
- pnpm workspaces (Node) + uv workspaces (Python)

## Project structure

Top-level only:
- `apps/web/` — Next.js frontend
- `apps/api/` — FastAPI backend + LangGraph runtime
- `apps/worker/` — Modal app (LLM + oracle workers)
- `packages/core/` — `capychem` core: loop, mutations, analyzer, oracle adapters
- `harness/` — pinned legacy `mol_opt` + PyTDC env (isolated)
- `infra/` — Docker Compose for Langfuse + Postgres dev
- `docs/` — milestones, handoffs, slice docs

## Critical constraints

- **NEVER** commit Modal, Langfuse, Postgres, OpenAI, Anthropic, or any provider secrets. Env vars only; `.env.local` is gitignored.
- **NEVER** claim real-world drug-discovery efficacy in code, copy, READMEs, or docs. Every score is an in-silico oracle score. Reflects PRD non-goal N6.
- **NEVER** import from or share a Python env with `harness/`. The legacy stack is pinned (PyTDC 0.3.6 / Python 3.10). Modern code calls the harness via subprocess with a typed JSON payload, never via `import`.

## Conventions

(Deviations from defaults only; rules a linter enforces aren't repeated here.)

- Python: ruff + mypy strict on new code under `apps/` and `packages/`. Existing pre-MVP code is grandfathered; raise strictness when touched.
- Validate every SMILES via RDKit before persistence. Never trust LLM output as valid.
- Wrap every LangGraph node in a Langfuse span. No silent loop steps.
- Frontend talks to FastAPI via an absolute URL for WebSockets; do not proxy WS through Next.js middleware (App Router quirks).
- Use positive imperatives in error messages and prompts: "Validate SMILES via RDKit" not "Don't skip validation."
- Cost tracking is a first-class field. Every LLM call and every oracle call updates `RunCost`.

## Gotchas

- `mol_opt` pins PyTDC 0.3.6 and Python 3.7–3.10. The legacy env lives in `harness/` as an isolated uv venv (`harness/.venv`, Python 3.10) — its own pyproject/lockfile, `package = false`, excluded from the root workspace. Modern code talks to it through `packages/core/capychem/oracle.py` via subprocess + JSON (wrapped by `apps/worker` for Modal in slice 4). Never `import` from harness or `uv add pytdc` into the modern env. PyTDC 0.3.6 also has incomplete deps: it needs `requests`/`networkx`/`scipy` declared explicitly and a one-symbol `rdkit.six` shim (modern RDKit dropped it) — both handled in `harness/`.
- DeepSeek-v4-pro cold start on Modal is ~30 s. The WebSocket layer must tolerate that: heartbeat-ping the client, buffer events, do not disconnect. Use Modal's warm-pool for active runs.
- The PMO success metric is **AUC of top-10 mean score versus oracle calls**, not the raw final top-1 score. The eval harness in `packages/core/eval` is the authoritative implementation; recomputing it ad hoc gives the wrong number.
- Langfuse traces are the source of truth for "what the agent decided this generation." Logs are secondary. When debugging a run, open Langfuse first.
- Modal LLM calls and oracle calls are charged independently. `RunCost.total_usd` must sum both; missing one means the cost gate (~$50/run) silently fails to fire.
- The analyzer step is the differentiator (MOLLEO has no analyze step). It is NOT optional — the closed-loop and agentic-depth claims both depend on it being present and functional.
- DeepSeek-v4-pro is used as both proposer and analyzer. If you change one prompt, sanity-check the other.

## Artifact conventions

Per `~/.claude/CLAUDE.md`:

- `docs/milestones.md` is the index of milestones; the one marked `← active` is current.
- Active milestone lives at `docs/NN-milestone/milestone.md` plus a `handoff.md` overwritten each session (20–40 lines).
- Vertical slices live at `docs/NN-milestone/NN-slice-name.md` (≤2 pages each).
- Planning artifacts from skills (design specs, implementation plans) land at the skill's default location (e.g., `docs/superpowers/specs/`, `docs/superpowers/plans/`) — do not relocate.
- Synthesize these files only when the work that backs them exists. Do not pre-create empty stubs.
- On session start, load: `docs/milestones.md` → active `milestone.md` → its `handoff.md`. The handoff's "Next session start here" line is the literal first action.
- On session end, overwrite `handoff.md`. Don't append; git preserves history.

When a slice ships, land all of these in one commit on the main-flow branch: milestone status flip, handoff status flip, "Next session start here" advance, slice-file freeze, dated "Slice N shipped" line appended to the milestone's `log.md` (never the handoff), commit refs under "Completed this session".
