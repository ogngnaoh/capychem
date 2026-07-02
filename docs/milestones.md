# Milestones

> Index of CapyChem milestones in execution order. The one marked `← active` is current. Per `~/.claude/CLAUDE.md`, synthesize each milestone's folder (`docs/NN-<name>/milestone.md`, `handoff.md`, slice files) only when work on that milestone starts — do not pre-create speculatively.
>
> Phases referenced below correspond to SPEC §9.

01. 00-walking-skeleton → docs/00-walking-skeleton/ — shipped (2026-06-12)
    Thin end-to-end slice (1 PMO task, no analyzer, minimal UI). Surfaces integration risk before rigor.
02. 01-harness-reproducibility → docs/01-harness-reproducibility/ — shipped (2026-06-16)
    SPEC Phase 1. Pinned harness env reproduces a Graph-GA PMO result; trivial LangGraph + Langfuse loop spike; per-run valid-SMILES measurement plumbed (>80% gate check rides with the LLM proposer in milestone 02).
03. 02-end-to-end-loop → docs/02-end-to-end-loop/ — shipped (2026-06-28)
    SPEC Phase 2. Modal LLM + worker pool; FastAPI REST + WS; Postgres; launch + watch-live on one PMO task; first beat-Graph-GA attempt.
    Slices: 01 launch-and-watch-jnk3 ✓ · 03 modal-llm-propose ✓ · 04 llm-proposer+ga-fallback ✓ · 05 unique-call-budget+cost-ledger ✓ · 06 beat-graph-ga finale ✓ (LLM beats GA on jnk3, week-7 kill-switch passed) · 02 plateau-stop ✓ (FR-003 plateau stop + live signal). All slices shipped → milestone complete.
04. 03-analyzer-and-scale → docs/03-analyzer-and-scale/ — shipped (2026-06-30)
    SPEC Phase 3. Analyzer agent (the differentiator); all 23 PMO tasks; cost gate; Week-8 bar (≥3/23 beat → on track).
    Slices: 01 analyzer-agent ✓ · 02 analyzer-value-verdict ✓ · 06 analyzer-conditioning ✓ (WIN +0.090/+0.108) · 04 twenty-three-task-surface ✓ · 05 week-8-sweep-and-gate ✓ (bar CLEARED, 7 beats) · 03 analyzer-live-surface ✓ (WS+REST+UI hypothesis surface). All slices shipped → milestone complete.
05. 04-compare-and-polish → docs/04-compare-and-polish/ — shipped (2026-07-01)
    SPEC Phase 4. Compare-runs flow; web polish; recruiter-legible README + Langfuse trace walkthroughs.
    Slices: 01 runs-list-and-browse ✓ · 02 compare-runs ✓ · 03 web-polish ✓ · 04 g1-full-23-sweep ✓ (G1 MET, 21/21 comparable) · 05 readme-and-langfuse-walkthrough ✓ (README + Langfuse walkthrough; folded in trace-link FR-014). All slices shipped → milestone complete.
06. 05-operator-workbench → docs/05-operator-workbench/ ← active
    UI/UX legibility redesign over the shipped engine: console-with-a-home workbench (Overview · Workbench · Runs · Compare), hybrid intent launcher, cockpit surfacing reasoning + beat-Graph-GA rigor. Agent-team Builder ↔ Critic, four human checkpoints.
    Slices: 01 low-fi-wireframes ✓ (CP1 approved) · 02 hifi-surfaces-and-launcher (in-progress) · 03 productionize-and-wire (planned). Slice 01 shipped (§8 decisions frozen); slice 02 (hi-fi) building → ⏸ Checkpoint 2 (visual) next.
