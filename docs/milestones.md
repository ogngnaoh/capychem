# Milestones

> Index of CapyChem milestones in execution order. The one marked `← active` is current. Per `~/.claude/CLAUDE.md`, synthesize each milestone's folder (`docs/NN-<name>/milestone.md`, `handoff.md`, slice files) only when work on that milestone starts — do not pre-create speculatively.
>
> Phases referenced below correspond to SPEC §9.

01. 00-walking-skeleton → docs/00-walking-skeleton/ ← active
    Thin end-to-end slice (1 PMO task, no analyzer, minimal UI). Surfaces integration risk before rigor.
02. 01-harness-reproducibility → docs/01-harness-reproducibility/ — planned
    SPEC Phase 1. Pinned harness env reproduces a Graph-GA PMO result; trivial LangGraph + Langfuse loop spike; >80% valid-SMILES gate.
03. 02-end-to-end-loop → docs/02-end-to-end-loop/ — planned
    SPEC Phase 2. Modal LLM + worker pool; FastAPI REST + WS; Postgres; launch + watch-live on one PMO task; first beat-Graph-GA attempt.
04. 03-analyzer-and-scale → docs/03-analyzer-and-scale/ — planned
    SPEC Phase 3. Analyzer agent (the differentiator); all 23 PMO tasks; cost gate; Week-8 bar (≥3/23 beat → on track).
05. 04-compare-and-polish → docs/04-compare-and-polish/ — planned
    SPEC Phase 4. Compare-runs flow; web polish; recruiter-legible README + Langfuse trace walkthroughs.
