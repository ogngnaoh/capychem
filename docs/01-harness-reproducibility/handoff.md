# Handoff — 01-harness-reproducibility (ACTIVE)

## Completed this session

- **PLAN phase complete for slices 1 & 2** (concurrent tracks). Each has, all committed to `main`:
  design spec (`docs/superpowers/specs/2026-06-15-{reproduce-graph-ga,langfuse-end-to-end}-design.md`),
  implementation plan (`docs/superpowers/plans/2026-06-15-*.md`), project slice doc
  (`docs/01-harness-reproducibility/0{1,2}-*.md`).
- **Architecture decided (via AskUserQuestion):**
  - Slice 1 — headless memoized eval runner (pure `top_auc` + no-DB runner, **unique-call** budget);
    product-loop memoization deferred to milestone 02; full 10k QED repro run in-slice.
  - Slice 2 — lightweight structural trace content; programmatic + manual-UI FR-014 verification;
    true run→generation→node nesting via `parent_observation_id` + an in-process gen-span registry.
- **Commits:** `f848583` spec-01 · `4728d03` spec-02 · `5a99f1c` both plans · (this commit) slice docs + handoff.

## Slice status across milestone

- `01-reproduce-graph-ga` → planned (PLAN done; ready to implement) — Track A
- `02-langfuse-end-to-end` → planned (PLAN done; ready to implement) — Track B (worktree-isolated, concurrent with A)
- `03-valid-smiles-measurement` → planned (not yet planned; Track A, sequential after slice 1)

## Current state

- `main` clean. No code yet — planning artifacts only. Modal oracle idle-cheap; `CAPYCHEM_ORACLE_BACKEND=local`.
- Langfuse v2 self-hosted on `:3001`; real keys in `.env.local` authenticate (SDK 2.60.10).

## Next session start here — IMPLEMENT phase, deploy the agent teams

Orchestrate IMPLEMENT for slices 1 & 2 **concurrently** via `superpowers:subagent-driven-development`. Per slice:
ONE TDD implementer through the plan tasks, then TWO fresh-context reviewers (spec-compliance vs the
spec/reference note + code-quality). **Slice 2's implementer runs WORKTREE-ISOLATED** (concurrent with slice 1).
YOU (orchestrator) own ALL doc writes + run the verification gate; teammates return structured results only.
- Load: this handoff · both specs · both plans · both slice docs · `agent_docs/pmo-auc-and-baselines.md`.
- Slice 1 worktree env: `CAPYCHEM_HARNESS_PYTHON=/Users/hoangngo/Documents/personal-projects/CapyChem/harness/.venv/bin/python`; leave `CAPYCHEM_ORACLE_BACKEND` unset.
- Gate per slice (paste REAL output): `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .`
- Checkpoints: STOP after each slice's VERIFY (before SHIP) and after SHIP. Stop at 40% context — overwrite this handoff.
- SHIP ritual (one commit on `main` per slice): milestone status flip · handoff overwrite + dated log line + commit refs · freeze slice file.

## Active concerns

- Slice 1: confirm `ValidCandidate`/`Scored` fields, `merge_and_truncate` sig, `load_starting_pop` path before finalizing the runner (adapter lines only — never the memoization logic).
- Slice 2: verify `parent_observation_id` accepted by `langfuse 2.60.10` (fallback: v2 stateful chaining).
- `pyproject.toml` shared edit: slice 1 `[project.scripts]`, slice 2 `[project.dependencies]` — trivial merge.
- Don't let a 2nd AUC definition drift: `eval/` is authoritative; `loop/logic.py`'s running curve = UI estimate only.
- Carried from 00: `GET /runs/{id}` cost_so_far_usd=0.0 fallback; top-10 sort triplicated; `Run.ended_at` unset — milestone-04 polish.

## Slice log

- 2026-06-12 — Milestone 01 scoped.
- 2026-06-15 — Slices 1 & 2 PLAN complete (specs + plans + slice docs committed); IMPLEMENT teams not yet deployed.
