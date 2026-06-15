# Handoff — 01-harness-reproducibility (ACTIVE)

## Completed this session

- **Milestone `01-harness-reproducibility` scoped.** Synthesized `milestone.md` (goal · scope · non-goals ·
  3-slice index · integration notes · exit criteria) at milestone altitude; slice details deferred to their
  own sessions per the planning-scope rule.
- **Two scoping decisions resolved** (via AskUserQuestion):
  - Valid-SMILES: **measure in 01, gate-check in 02.** No LLM exists yet, so 01 ships the measurement
    plumbing (exercised on Graph-GA, ~100% valid by construction); the >80% pass/fail check rides with the
    LLM proposer in milestone 02.
  - Langfuse: **provision real keys now** so the trace-verification slice can actually close in 01.
- **Key finding:** the canonical AUC harness (`packages/core/eval`) does **not exist yet** — `loop/logic.py`
  calls its own running curve "un-authoritative" and points at `packages/core/eval` as "later." Slice 1 is
  where that contract first becomes real. Graph-GA proposer + QED oracle bridge already work; no LLM anywhere.
- **Reference note written** (subagent, source-verified): `agent_docs/pmo-auc-and-baselines.md` — the exact PMO
  `top_auc` implementation + published Graph-GA per-task table. QED diff target = **0.940 ± 0.000** (PMO Table 2);
  reproduction tolerance **±0.02 absolute**. Removes the slice-1 TBDs before they reached the slice session.

## Slice status across milestone

- `01-reproduce-graph-ga` → planned (load-bearing: build `packages/core/eval` + `capychem-eval`, reproduce Graph-GA AUC)
- `02-langfuse-end-to-end` → planned (provision keys, verify nested trace, FR-014)
- `03-valid-smiles-measurement` → planned (per-run valid-SMILES rate; gate check is milestone 02)

## Current state

- `main` is clean and pushed to `origin/main` (`1105675`). Walking skeleton closed (2026-06-12).
- Modal `capychem-worker` (oracle) stays DEPLOYED, idle-cheap — left up by default (housekeeping was "your call").
- Default `CAPYCHEM_ORACLE_BACKEND=local` keeps dev/CI Modal-free.
- No code written — milestone scoping only. **`docs/01-harness-reproducibility/` and `agent_docs/pmo-auc-and-baselines.md`
  are UNTRACKED** (not yet on `main`); commit them before/with slice-1 work so they don't vanish.

## Next session start here

**To run the whole milestone via agent teams:** paste the master orchestrator prompt at
`~/Documents/personal-vault/meta-workflows/2026-06-15-capychem-milestone-01-agent-team-kickoff.md` into a fresh
session — one orchestrator drives all 3 slices (plan→implement→verify) with checkpoints, owning all doc writes.
Otherwise, to do slice 1 solo:

Scope and execute **slice `01-reproduce-graph-ga`** in its own session: build `packages/core/eval` (the
canonical AUC-of-top-10-mean-vs-oracle-calls harness) + the `capychem-eval` CLI entrypoint, run vanilla
Graph-GA on QED through the isolated `harness/` env, and diff our AUC against the published PMO Graph-GA
number within a chosen tolerance. Produce the slice's design spec + implementation plan there (not here).

## Active concerns

- **User action required:** provision real Langfuse keys (self-hosted via `infra/langfuse-compose.yml` or
  cloud) before slice 2 can close. Keys go in `.env.local` / env only — never commit (SPEC §8.1).
- **Reproduction gotchas (from the reference note) the slice MUST honor:** pass `mutation_rate=0.067` to the
  harness proposer (the `propose.py` docstring example shows `0.01` — wrong; mismatch shifts AUC). Implement
  `top_auc` faithfully: trapezoidal, sampled every `freq_log=100`, `finish=True` to pad the tail, normalized
  `÷ max_oracle_calls=10000`; budget counts **unique** (memoized) oracle calls. QED reproduction is a smoke
  test only — its ±0.000 std makes a broken metric unambiguous, but it has near-zero beat-headroom (that's 02).
- Don't let a second AUC definition drift: `packages/core/eval` is authoritative; `loop/logic.py`'s curve is
  demoted to a live-UI estimate only.
- Carried from 00: `GET /runs/{id}` DB-read fallback reports `cost_so_far_usd=0.0`; top-10 sort key
  triplicated; `Run.ended_at` unset — all milestone-04 polish.

## Slice log

- 2026-06-12 — Milestone 01 scoped; decisions logged (valid-SMILES measure-in-01/check-in-02; Langfuse keys now).
