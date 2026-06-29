# Design — Analyzer Conditioning Redesign (evidence-first)

**Status:** Draft (brainstorm output, pre-plan)
**Date:** 2026-06-29
**Milestone:** 03 `analyzer-and-scale` (would become slice 06, after the {01,02} pair)
**Related:** SPEC §6.4b · slice-02 verdict (`docs/03-analyzer-and-scale/02-analyzer-value-verdict.md`) · PROJECT §9 kill-switch
**Authoritative re-verify harness:** `eval/verdict.py` (`--analyzer-verdict`), now trustworthy (parse-rate-guarded, analyzer reasoning-OFF)

## 1. Problem

Slice 02 rendered a **trustworthy clean NULL**: on jnk3 @ seed 42, budget 10 000, the analyzer
*hurts* — with-analyzer AUC **0.678** vs without **0.743** (−0.066), parse-rate 1.0, valid-rates
healthy. The analyzer's `{focus, avoid}` conditioning, applied on top of an LLM proposer that already
beats Graph-GA unaided, makes the loop worse. Per PROJECT §9 this is a pivot signal — but we are
choosing to **treat it as a fixable conditioning problem and chase AUC value**, not abandon the
differentiator.

### Inferred mechanism (from the code path, not yet from traces)

Tracing `analyzer.py` → `strategy.build_analyzer_prompt` → `parse_hypothesis` →
`strategy.build_prompt`, the strongest-to-weakest inferred causes:

1. **Hard directive, whole batch, every generation.** `build_prompt` injects *"focus on {focus};
   avoid {avoid}"* as an instruction into all 70 offspring prompts for ~35 generations. One hypothesis
   steers the entire batch identically → diversity collapse + correlated bias on a process that was
   already exploring well.
2. **No headroom on jnk3.** jnk3 is a bioactivity oracle where the proposer recalls known active
   chemotypes from pretraining (that is *why* it beats GA). Generic med-chem guidance from the same
   model pulls it *off* the high-scoring manifold.
3. **`avoid` is an asymmetric prune.** A wrong `focus` is a soft nudge; a wrong `avoid` is a hard
   negative constraint that can exclude exactly the substructure the best binders need.
4. **Reasoning-OFF made the hypothesis trustworthy but possibly shallow.** We flipped reasoning OFF
   in slice 02 to fix parse-rate, not analytical quality — so we now reliably parse a possibly-shallow
   pattern-name.

**These are inferred, not proven.** We never persisted a single real hypothesis text from the slice-02
run — only AUC. Closing that gap is the first deliverable.

## 2. Goal & success criteria

- **G:** On jnk3 @ seed 42, budget 10 000, flip the analyzer verdict from −0.066 to **diff ≥ 0**
  (with-analyzer ≥ without-analyzer) via redesigned conditioning, re-measured by the canonical
  `--analyzer-verdict` harness, with parse-rate ≥ 0.8 and both valid-rates ≥ ~0.8 (the slice-02 guards).
- **Stretch:** a positive diff, not merely a non-negative one.
- **Falsifiable null:** if the matched fix still nulls *with a clean trace explanation of why*, that is
  itself a publishable result and strengthens the analyzer-only-narrative pivot (it would show the
  conditioning, not the wiring, is the limit on jnk3 specifically).

## 3. Non-goals

1. **23-task sweep / Week-8 bar** — slice 05; this slice stays single-task (jnk3), single-seed (42), to
   isolate the conditioning change.
2. **Analyzer-only-narrative pivot** — explicitly deferred; we are chasing AUC value first.
3. **Live-surface / WS / UI** (slice 03) and **product-loop graph.py changes** beyond what parity demands.
4. **Multi-seed robustness** — one seed (42) to keep the comparison cheap and apples-to-apples with the
   slice-02 baseline; a second seed is a follow-up, not in scope.
5. **New oracle / model / Modal work.**

## 4. Approach — evidence-first, four phases

The slice is structured so the **trace read selects the fix**. We do not shotgun all levers.

### Phase 1 — Instrument & capture (deterministic; cheap, ~$0.15)

Add a **trace-collection path** to the headless runner that records, per generation:
`AnalyzerSummary` (top-k/bottom-k it saw), the raw analyzer output, the parsed `{focus, avoid}`, the
resolved effective hypothesis, and the **exact conditioned vs unconditioned proposer prompt** for that
generation. Emit as JSON/JSONL.

- **Interface:** `run_reproduction(..., trace_sink=...)` — an optional collector (callback or list)
  populated at the analyzer + propose seams; `None` (default) ⇒ byte-identical to today (G6 preserved).
- **CLI:** a `--capture-analyzer-traces` mode in `eval/cli.py` (mirrors the `--analyzer-verdict`
  flag-per-mode pattern) that runs jnk3 `direct`, analyzer=True, budget ~300, seed 42, and dumps traces.
- **Cost:** budget-300, single arm (with-analyzer only) ⇒ well under $0.20.
- **Reusable:** every later conditioning experiment reads these traces.

### Phase 2 — Diagnose from traces

Classify the dominant failure into exactly one primary bucket (record the read in the slice doc):

| Trace finding | Dominant mechanism | Primary fix |
|---|---|---|
| Hypotheses are *reasonable* but the conditioned prompt forces the batch one way | **Application** (1, 3) | **Approach A** |
| Proposer's top-10 was *climbing* and conditioning bent a working trajectory | **Timing** (2) | **Approach B** |
| Hypotheses are *generic / wrong / noise* | **Content** (4) | **Approach C** |

A's softening can layer onto B or C, but the evidence picks the *primary* lever.

### Phase 3 — Apply the matched fix

**Approach A — Soften & diversify the application** *(touches only `strategy.build_prompt`)*
Keep the `{focus, avoid}` output; change how it is used:
- reframe directive → optional inspiration: *"Analysis of the last generation suggests X may help;
  weigh it against your own chemical judgment"*;
- drop or demote `avoid` (remove the hard negative, or reframe as "these scored lower" observation);
- condition only a fraction (≈⅓–½) of the `offspring` prompts, leaving the rest unconditioned to
  preserve batch diversity and hedge a bad hypothesis.
Smallest, most surgical change. Directly attacks mechanisms 1 & 3. **Recommended default if the
evidence is ambiguous.**

**Approach B — Gate the analyzer to plateaus** *(touches the conditioning decision in `runner.py` +
`loop/graph.py` for parity)*
Let the unconditioned proposer run until its top-10 mean flattens (reuse the existing recent-trajectory
signal), *then* inject guidance to break the plateau. Structurally protects the "no headroom" case — the
analyzer acts only when the proposer has actually stalled. More loop logic (a plateau gate on the
conditioning), and the hypothesis is still produced every gen (for the live surface) but applied
selectively.

**Approach C — Change what the analyzer produces** *(touches `build_analyzer_prompt`, `parse_hypothesis`,
and the `build_prompt` injection)*
Switch from prescriptive `{focus, avoid}` to **descriptive structural observations** ("top scorers share
an aromatic core with a basic nitrogen"), which the proposer uses freely rather than as a command.
Optionally restore reasoning depth via a parse-safe path (structured output / two-call). Largest change;
reintroduces some parse/cost risk — so it carries the slice-02 parse-rate guard forward as a gate.

### Phase 4 — Re-verify

Run `--analyzer-verdict` on jnk3 @ seed 42, budget 10 000 (`direct` both backends). Read the verdict
**with the slice-02 caveats**: confirm `parse_rate_healthy` AND both `*_valid_rate` ≥ ~0.8 (a depressed
valid-rate means a balance-exhaustion degradation, which `parse_rate_healthy` does NOT catch — see
slice-02 notes). Record the diff + the kill-switch read in the slice doc.

## 5. Components & boundaries

- **`eval/runner.py`** — add the optional `trace_sink` seam (Phase 1) and, for Approach B, the
  conditioning gate. The `trace_sink=None` default keeps the existing path byte-identical (G6).
- **`eval/cli.py`** — `--capture-analyzer-traces` mode (Phase 1 output).
- **`loop/strategy.py`** — `build_prompt` softening (Approach A) and/or `build_analyzer_prompt` +
  output-shape change (Approach C). This is the shared module both paths import (G6 parity).
- **`analyzer.py` / `parse_hypothesis`** — only if Approach C is selected (new output schema).
- **`loop/graph.py`** — only if Approach B's gate must reach the product loop for parity (criterion-1
  both-paths requirement); otherwise untouched.

The trace-capture seam and each approach are independently testable on the `stub`/monkeypatched path.

## 6. Testing

- **TDD on `stub`/monkeypatched backends** (free, deterministic) per code change, matching slice-02
  discipline. Gate each task: `uv run pytest` · `uv run mypy -p capychem -p capychem.api` ·
  `uv run ruff check .`.
- **Phase-1 trace seam:** assert the collector captures the conditioned prompt and that `trace_sink=None`
  leaves `build_prompt`/runner output unchanged (a regression test pinning byte-identical behavior).
- **Approach A:** assert the softened prompt contains the inspiration framing, omits the hard `avoid`
  directive (or whichever demotion is chosen), and that the unconditioned fraction is genuinely
  unconditioned; gen-1 / graph_ga prompts stay byte-identical (the existing regression).
- **The real `direct` runs (Phase 1 capture, Phase 4 verdict)** are the load-bearing manual checks — every
  score an in-silico oracle score (PRD N6).

## 7. Cost / balance

DeepSeek prepaid balance ≈ $1 at slice start; a full `--analyzer-verdict` re-run ≈ $1, Phase-1 capture
≈ $0.15. **Top up the balance before Phase 4.** Dollar cost is non-binding for this project
(real tolerance < $50 total); the practical limiter is the prepaid balance, not policy — so plan to
top up rather than ration variants. Finishability + a clean result are the real risks, not spend.

## 8. Open questions (resolve during planning / from traces)

- **Approach selection is deferred to the Phase-2 trace read** — by design (user chose "spec all three,
  evidence picks at Phase 2").
- **Conditioned fraction for Approach A** (⅓ vs ½) — pick from the trace read of how much diversity the
  full-batch conditioning was costing.
- **Whether `avoid` is dropped vs demoted** in Approach A — depends on whether traces show `avoid` doing
  specific harm vs being merely inert.
- **Does Approach B's gate need to reach `graph.py`** this slice, or is headless-only acceptable until the
  live surface (slice 03) lands? Criterion-1 wants both paths eventually; the *verdict* only needs the
  headless path.
