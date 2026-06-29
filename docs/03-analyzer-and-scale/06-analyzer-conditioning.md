# Slice 06 — analyzer-conditioning (redesign)

> Milestone 03 `analyzer-and-scale`. Added after slice 02's clean NULL (build order: `01 → {02 ∥ 03 ∥ 04} → 05`, with **06 inserted as the analyzer-iteration response to the slice-02 kill-switch**, ahead of 05). Deps: 01 ✓, 02 ✓ (the verdict that motivates this).
> Design: `docs/superpowers/specs/2026-06-29-analyzer-conditioning-redesign-design.md` ·
> Plan: `docs/superpowers/plans/2026-06-29-analyzer-conditioning-redesign.md`.

## Goal

Flip the analyzer from value-negative to value-neutral-or-positive on jnk3 by redesigning how its
`{focus,avoid}` hypothesis conditions the proposer — **evidence-first**: capture the real hypotheses,
diagnose the dominant failure, apply the one matched fix, re-verify with the canonical
`--analyzer-verdict` harness (slice-02 trustworthy: parse-rate guarded, reasoning-OFF).

## Plan

Headless `eval/` + shared `loop/strategy.py` only — no product-loop/WS/UI/DB change (the verdict needs
only the headless path; `strategy.py` edits reach both paths for free). Four phases:

1. **Capture (Tasks 1–2):** a `trace_sink` seam in `run_reproduction` + a `--capture-analyzer-traces`
   CLI mode → a cheap jnk3 `direct` budget-300 run logs each generation's `{focus,avoid}` + the
   conditioned vs unconditioned proposer prompt.
2. **Diagnose (gate):** classify the failure as Application / Timing / Content from the traces.
3. **Matched fix (Task 3, ONE of):** **3A** soften the directive to optional inspiration + demote
   `avoid` + condition only a fraction of the batch (`strategy.py`); **3B** gate conditioning to
   plateaus, reusing `logic.is_plateau` (`runner.py`); **3C** descriptive observations instead of
   prescriptive directives (`strategy.py` + `analyzer.py`).
4. **Re-verify:** `--analyzer-verdict` jnk3 @ seed 42, budget 10000; accept if `diff ≥ 0` with both trust
   guards healthy (parse-rate ≥ 0.8 AND both valid-rates ≥ ~0.8).

## Tasks

- [ ] T1 — `eval/trace.py` `GenerationTrace` + `trace_to_dict`; `trace_sink` seam in `run_reproduction`; trace tests (TDD).
- [ ] T2 — `--capture-analyzer-traces` CLI mode; CLI test (TDD).
- [ ] **GATE** — run the budget-300 jnk3 `direct` capture; classify Application/Timing/Content; record the read here.
- [ ] T3 — implement the ONE matched approach (3A default / 3B / 3C) per the gate; TDD on stub.
- [ ] **VERIFY** — `--analyzer-verdict` jnk3 @ seed 42 budget 10000; record diff + trust guards + kill-switch read here.
- [ ] Gates green: `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .`.

## Notes

- **Evidence-first is load-bearing:** the diagnosis (slice-02 handoff) is *inferred from the code path*,
  not proven — no real hypothesis text was ever persisted. Do not skip the GATE; it picks the fix.
- **No-headroom risk:** jnk3 is the hardest task for the analyzer (LLM prior strongest). A clean
  trace-backed null is still a valid result; the authoritative bar is the slice-05 23-task sweep.
- **Balance:** DeepSeek prepaid ≈ $1 — top up before VERIFY (full run ≈ $1; capture ≈ $0.15). Confirm the
  balance covers the run: a mid-run $0 silently degrades the LLM arm to Graph-GA, which `parse_rate_healthy`
  does NOT catch — cross-check both valid-rates ≥ ~0.8 ([[project_eval_compute_budget]]).
- **Reuse:** 3B reuses `logic.is_plateau` (no new helper); 3A extends `propose_llm_async` (no parallel fn).
- **Parity deferral (3B only):** if 3B is chosen, `loop/graph.py` needs the same gate before the live
  surface (slice 03) for criterion-1 both-paths parity — a follow-up, not a blocker for the verdict.
- **Scope:** one task (jnk3), one seed (42). A second seed (7) would harden any result (~$1 more) — out of
  scope here.
- **Out of scope / deferred:** 23-task sweep (slice 05); analyzer-only-narrative pivot (deferred — chasing
  AUC first); live surface (slice 03).
