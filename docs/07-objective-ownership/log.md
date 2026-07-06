# Log — milestone 07 objective-ownership

Append-only. Dated rationale/findings a diff can't show. Git records what shipped.

## 2026-07-06 — Slice 07-08 BACKEND WIRING shipped (UI deferred to a fresh session)

The operator chose to land 07-08's backend wiring now and build the visual UI in a fresh,
screenshot-iterated session (their usual frontend workflow). Backend findings:

- **Novelty needed the gen-0 seed set stashed once.** `_persist` stashes
  `seed_pop = {survivor smiles}` into `LoopState` ONLY at gen 0 (later generations never
  overwrite it); `stop_check` + the 3 runner-fallback `build_summary` calls pass it, so a
  real run's `summary_json.novelty` = fraction of the final population not among the starting
  molecules. The **resume** path can't reconstruct the gen-0 seed from DB rows → novelty null
  there (best-effort, documented).

- **The live snapshot shadows the DB path for completed runs** (the handle is never evicted),
  so putting quality/diversity/novelty only in `summary_json` wouldn't surface them on a
  post-completion GET. Fix: the runner **overlays** `top_k` (with quality) + `diversity` +
  `novelty` onto `handle.snapshot` at finalize, alongside the terminal status. The DB path
  also reads them from `summary_json` (for runs not in the registry).

- **Quality on top-K is recomputed in `build_summary`**, not joined from `Candidate.quality_json`.
  build_summary is finalize-only (the heavy O(n²) diversity already lives there), so
  recomputing `molecule_quality` for the top-10 is negligible AND keeps the live path (no DB)
  and DB path identical. One consequence: `test_build_summary_shape` asserted the exact top_k
  dict — updated to check smiles/score + `quality.valid` (the intentional shape change).

- Gate: mypy (66) · ruff · **396** backend (+2: build_summary top_k quality unit + a completed-
  run snapshot e2e asserting diversity/novelty/top-K-quality) · web typecheck/ESLint · 40
  vitest · benchmark unchanged. **Milestone 07 backend is now complete; only the UI remains.**

## 2026-07-06 — Slice 07-07 lineage export shipped

CSV + SDF lineage export. Findings:

- **SDF must `flush()`, never `close()`, the StringIO.** `Chem.SDWriter(buf)` needs a flush
  to emit the trailing `$$$$` record terminator, but `writer.close()` also closes the
  underlying `StringIO`, after which `buf.getvalue()` fails. `writer.flush()` emits the
  terminator and leaves the buffer readable. Verified the round-trip:
  `Chem.ForwardSDMolSupplier(BytesIO(sdf.encode()))` re-reads the mols + props.

- **Hypothesis-at-birth = the hypothesis after gen g-1.** The analyzer produces a hypothesis
  AFTER generation N, which conditions gen N+1's proposals. So a candidate in generation g
  was born under `AnalyzerHypothesis.after_generation_index == g-1` (null for gen 0/1).

- **Quality flattened into columns.** `_lineage_rows` reads `Candidate.quality_json` (07-05)
  and spreads its keys into fixed CSV columns / SDF props, so an exported file is a flat,
  tool-agnostic table. Manifest git-SHA + PyTDC pin ride as SDF props so the file is
  self-describing.

- Purely additive, read-only routes — no model/loop change, no migration. Gate: mypy (66) ·
  ruff · **394** backend (+3) · benchmark untouched.

## 2026-07-06 — Slice 07-06 provenance manifest shipped (OD-5)

The harness finally emits its own version; every run gets a citable manifest. Findings:

- **`importlib.metadata.version("PyTDC")`, not `tdc.__version__`.** `tdc` has no
  `__version__` attribute (returns "?"); the distribution name is `PyTDC` and
  `importlib.metadata.version("PyTDC")` → "0.3.6" in the legacy venv. OD-5 wanted the REAL
  installed version, so the harness reads it at emit time (best-effort, "unknown" on failure).

- **`pytdc_version()` is cached + short-timeout — the version is a process constant.** It
  probes the local harness (`_run_scorer([], "qed")` — qed is analytic, empty SMILES so
  nothing is scored) with a 15s timeout and `@lru_cache(maxsize=1)`, so a run's finalize
  spawns at most ONE probe per process (not per run) and never blocks 120s on a hung
  harness. Crucially it uses the LOCAL harness directly, independent of
  `CAPYCHEM_ORACLE_BACKEND`, so no Modal-worker mirror was needed (the plan's mirror step
  was unnecessary).

- **Manifest built once at finalize; oracle_version backfilled in one UPDATE.** Rather than
  stamp `OracleCall.oracle_version` per call (a subprocess tax at score time) or per run
  start (latency on every launch), `finalize_run` writes `Run.manifest_json` AND
  `UPDATE oracle_calls SET oracle_version=<pin> WHERE run_id=…` in one shot at the end.

- **`score_smiles` refactored to delegate to `_run_scorer`** (extracted subprocess+parse) so
  `score_smiles` and `pytdc_version` cross the harness boundary the one sanctioned way. All
  existing oracle/eval tests pass unchanged — the refactor is byte-identical.

- **Everything is best-effort/nullable.** git_sha (not a checkout → None), model_id, PyTDC
  pin (harness down → None), trace_url (Langfuse off → None). A manifest never fails a run.

- Gate: mypy (66 files) · ruff · **391** backend (+5, incl. a real-run e2e asserting the
  manifest carries the real 0.3.6 pin + a git SHA + model id) · migration drift · benchmark
  unchanged.

## 2026-07-06 — Slice 07-05 quality & trust layer shipped

Per-candidate quality report + run-level diversity + a shared trust-gate home. Findings:

- **Quality is annotate-only (OD-4) — the whole point.** `molecule_quality` is computed at
  persist and written to `Candidate.quality_json`; it NEVER drops or reorders a candidate,
  so a benchmark run's top-10 is byte-identical to pre-07-05. That's the OD-4 contract:
  benchmark comparability is sacred, the reward-hacking defense is a *read*, not a filter.
  (The exploratory hard-drop toggle isn't in the acceptance and wasn't built.)

- **`build_summary` gained an RDKit dependency — lazy-imported.** Diversity/novelty need
  Morgan FPs, but `loop/logic.py` is the "pure decision helpers" module imported everywhere.
  A top-level `from capychem.quality import …` would pull RDKit + the FilterCatalog builds
  at every import of logic. Lazy import *inside* build_summary defers that to the one call
  site that needs it.

- **Novelty is half-wired on purpose.** The helper + `build_summary(seed_pop=…)` param exist
  and are unit-tested, but threading the canonical gen-0 seed set through the live
  stop_check + 4 runner fallback build_summary calls (+ resume) is real churn for a secondary
  metric. Deferred to 07-08 (the UI slice that surfaces it). **Diversity** is self-contained
  and already surfaces in every run's summary_json.

- **`_PARSE_RATE_FLOOR` unified via alias-import.** `eval/beat.py` and `eval/verdict.py`
  each had `_PARSE_RATE_FLOOR = 0.8`. Moved the single source to `trust/gates.py::PARSE_RATE_FLOOR`;
  both now do `from capychem.trust.gates import PARSE_RATE_FLOOR as _PARSE_RATE_FLOOR` —
  keeps their internal name, one source of truth (a test asserts `is` identity).

- **Test data gotcha:** aspirin trips a **Brenk** alarm (acetate ester / carboxylic acid),
  so it's NOT a clean-molecule fixture. Used **caffeine** for the clean drug-like case and
  **hydroquinone** for the alarm case (both verified against the catalogs).

- Gate: mypy (65 files) · ruff · **386** backend (+9: quality + trust + a persist e2e that
  asserts top-K candidates carry a report) · migration drift · benchmark top-10 unchanged.

## 2026-07-06 — Slice 07-04b constraints shipped

Hard structural constraints at the validity gate + a distinct constraint-starvation
signal. Findings:

- **Constraint-failing = invalid.** Constraint-failing molecules are dropped at the score
  node BEFORE scoring — no oracle budget spent, same treatment as an RDKit-invalid SMILES
  (FR-005 GA-fallback keeps throughput). No constraints ⇒ the filter is skipped entirely,
  benchmark byte-identical.

- **Starvation ≠ plateau ≠ no_progress.** A generation whose candidates ALL fail the
  constraints is "starved" (`_constraint_starved`). The subtlety: a starved gen makes no
  progress, so naive logic would fire `no_progress` after one generation and mask the real
  cause. Fix: a starved gen never triggers no_progress — `stop_check` accumulates a streak,
  and only a *sustained* streak (≥ `plateau_window`) terminates as `constraint_starved`.
  Plateau/no_progress apply only to non-starved generations.

- **Known limitation — gen-0 total starvation → no_progress, not constraint_starved.**
  If constraints reject the *entire* gen-0 population, the survivor pool empties; the next
  generation then proposes nothing (candidates empty ⇒ not "starved"), so the run stops as
  `no_progress`. The distinct `constraint_starved` reliably fires only when candidates keep
  being proposed but keep failing for a full window (population persists). The mechanism is
  unit-proven; a full-loop starvation e2e is fragile (depends on the empty-population edge),
  so it wasn't added. Acceptable — the run still terminates cleanly either way.

- **`runs.status` widened `String(16)`→`String(32)` (migration `ed2d80a8ccda`).**
  `constraint_starved` is 18 chars and would overflow the old column on Postgres (sqlite
  doesn't enforce varchar length, so unit tests wouldn't catch it — caught by inspection).
  Widened once with headroom. `constraint_starved` needs no special status-branch handling
  (it's terminal like plateaued/exhausted; unlike `paused`, no resume action).

- **Soft property bands need NO new code.** A MW/logP/TPSA band is a descriptor-oracle
  objective term (07-03/07-04) with a `double_sigmoid` transform. constraints.py is
  HARD-only (SMARTS/catalog). Documented, not reimplemented.

- Gate: mypy (61 files) · ruff · **377** backend (+15: constraints/stop_reason + score-node +
  route) · migration drift · web untouched.

## 2026-07-06 — Slice 07-04 objective composition shipped (split from plan Task 07-04)

Composed multi-term objective → one [0,1] scalar, consumed by the loop. Findings:

- **The score node's objective branch fires ONLY when `objective_json` is present.**
  The no-objective path is the *original code, unchanged* (same lines) — so the benchmark
  is byte-identical by construction, not by a parity argument. The composed branch is
  additive. This is the zero-risk way to consume the objective (vs. routing benchmark
  through a single-term objective and hoping it stays identical).

- **Dependency-injected `pmo_scorer` keeps the harness path intact.**
  `Objective.evaluate_async(smiles, *, pmo_scorer)` — a PMO term calls the injected scorer
  (the loop's retry-wrapped `score_batch_async`), so cost/backend/retry are preserved and
  untouched; descriptor terms score sync in a thread, cost 0. The objective layer only
  ADDS transform + aggregation; it never reimplements scoring. Budget stays per-candidate
  (OD-2): one objective eval = one unique call regardless of term count.

- **Direction normalizes at the transform, not the loop.** A `minimize` oracle in a
  composed objective uses `reverse_sigmoid`/`double_sigmoid`, so the aggregate is always
  maximize-in-[0,1] and the loop/AUC never need the 07-03 `direction` params (those are for
  a *bare* single-oracle run). Aggregators (`weighted_sum`, weighted-geometric-mean
  `weighted_product`) both reduce to the raw value for a single term — so a single identity
  term == the raw oracle.

- **A test that "passes" without the feature is a bug in the test.** The first score-node
  objective test used a single *identity* PMO term, which equals the raw benchmark score —
  so it passed whether or not the objective branch existed. Fixed by using a `sigmoid`
  transform whose output ≠ the raw value, so it genuinely fails on the benchmark path.

- **Split:** plan Task 07-04 bundled constraints; that would push the working doc past 2
  pages and enlarge the loop change. Constraints (SMARTS `FilterCatalog` at the validity
  gate + property bands + starvation-≠-plateau) are slice **07-04b**.

- Gate: mypy (59 files) · ruff · **362** backend (+16: 9 objective + 2 score-node + 4 route +
  1 real-app e2e; all eval/benchmark tests byte-identical). `Run.objective_json` (07-01 column)
  now populated; no new migration.

## 2026-07-06 — Slice 07-03 pluggable ScoringOracle shipped

The pluggable scoring seam + presets + direction, proven at parity. Findings:

- **`oracle.py` → `oracle/__init__.py` verbatim, NOT a re-exporting shim.** The
  refactor trap: `test_oracle_backend` does `from capychem import oracle` then
  `monkeypatch.setattr(oracle, "score_smiles", …)` and relies on `score_batch_async`
  reading `score_smiles` from the *same* namespace. A `bridge.py` + re-export `__init__`
  would break that (the patch would hit the package attr, not the bridge global). Moving
  the file verbatim into `__init__.py` keeps one namespace — zero test/import changes. The
  new submodules (`protocol`/`registry`/`pmo`/`descriptors`/`admet`) are imported by full
  path and are NOT imported from `__init__`, so there's no partial-init cycle. Gotcha: the
  `_REPO_ROOT = parents[3]` path calc became `parents[4]` (file moved one level deeper).

- **The protocol uses read-only `@property` members, not bare attributes.** A frozen
  `DescriptorOracle` (value object) has read-only fields; a `Protocol` with `name: str`
  (read-write) rejects them (`Callable[[], DescriptorOracle]` not assignable to
  `Callable[..., ScoringOracle]`), while a plain-attribute class like `PmoOracle` passes.
  Read-only property members are satisfied by BOTH a mutable attribute and a frozen field —
  the correct permissive contract.

- **`direction` normalizes at the objective (07-04), not the loop.** Threaded
  `direction="maximize"` into `_sort_key`/`merge_and_truncate`/`build_summary`/
  `build_analyzer_summary`/`top_auc` (default byte-identical) so a *bare* single minimize
  oracle ranks right, but the real design keeps the loop/AUC always-maximize by having
  07-04's transforms flip a minimize oracle into maximize-in-[0,1]. The threaded params are
  the fallback for a standalone exploratory oracle run.

- **Scoping: 07-03 is the library, 07-04 is the wiring.** The loop/route consuming a
  `ScoringOracle` needs the score+valid+cost contract that only exists once the objective
  boundary is defined (OD-2 per-candidate budget). Rewiring in 07-03 would be a throwaway
  PMO-specific method. "Routes through PmoOracle" is satisfied by the parity test
  (`PmoOracle(task).score == [r.score for r in score_smiles(...)]`); eval/runner.py (the
  authoritative G1 path) is untouched.

- **SA-score is RDKit Contrib, not an installable package** — `sys.path.append(
  RDConfig.RDContribDir/SA_Score)` then `import sascorer` (+ `# type: ignore[import-not-found]`).
  ADMET-AI is import-guarded (module imports clean without `admet_ai`; model lazy-loaded;
  registered only when available).

- Gate: mypy (58 files) · ruff · **346** backend (+10 oracle tests; all eval/benchmark tests
  byte-identical under the maximize default). No schema change; web untouched.

## 2026-07-06 — Slice 07-02 seed-SMILES plumbing shipped

FR-001: an operator's bring-your-own compounds now reach the gen-0 population. Findings:

- **`seed_smiles` is a `list[str]`, never the RNG `seed`.** The integer RNG `seed` (G6
  reproducibility) and the seed *population* are distinct concepts; the plan flagged the
  hazard of overloading one for the other. A dedicated `list[str]` column + LoopState key
  keeps them orthogonal — a test asserts `cfg.seed == 42` is untouched by a custom seed.

- **Gen-0 tops up from the shipped pool.** The plan's "GA-filled from the shipped pool or
  truncated to exactly pop_size" resolves to: canon+dedup operator seeds (they lead), then
  fill remaining slots from the shipped starting pool (skipping dups) up to `pop_size`
  (truncate if the operator gives more). Top-up guarantees the ≥2 parents crossover needs.
  Trade-off: a tiny custom seed set is diluted by generic fill — acceptable for a GA that
  needs diversity, and it's exploratory-only anyway.

- **The `/runs` boundary validator is authoritative.** The intent-preview already validated
  a *single* seed, but a client can POST `/runs` directly, so the Pydantic `field_validator`
  on `CreateRunRequest.seed_smiles` RDKit-checks each entry, drops empties, and collapses an
  all-empty/`[]` list to `None` (so it stays `benchmark` via `derive_mode`). The intent
  preview stays best-effort; the Launcher only sends a seed to it when exactly one is parsed,
  so a valid multi-seed list is never falsely refused there.

- **Two test roots, one rootdir, no `__init__.py`** → test file basenames must be unique
  across `packages/core/tests` and `apps/api/tests`, or pytest errors on an import-file
  mismatch. Renamed the API test to `test_seed_plumbing_route.py`.

- **Single-line `<input>` strips newlines** (DOM), so the 07-02 seed field is space/comma
  separated; multi-line SDF/CSV paste with an accepted/rejected list is deferred to 07-08.

- Gate: mypy (53 files) · ruff · **336** backend (was 325; +6 core, +5 API incl. a real-app
  end-to-end drive) · web typecheck + ESLint · 40 vitest · migration drift gate. Alembic head
  `b4ea6a051441`; dev DB upgraded (571 rows backfilled `seed_source="default"`).

## 2026-07-06 — Slice 07-01 run-mode-split shipped

The benchmark/exploratory invariant carrier. Findings worth keeping:

- **Eval ingestion needs no mode gate.** The plan (Task 07-01) listed "eval/* ingestion (only `mode==benchmark` feeds top_auc/baselines)". On inspection the eval pipeline (`eval/runner.py`, `beat.py`, `verdict.py`) runs its own in-process loops with **no DB-run ingestion** — it never reads `Run` rows. So the contamination risk is purely on the **API presentation side** (a run's snapshot showing a Graph-GA "beat"). The single gate is `_gated_baseline(mode, task)` in `routes_runs.py`, applied on both the live and DB snapshot paths. No eval code changed.

- **`figure_canon` states the prose canon, not a raw row count.** The g1 sweep JSON banks 21 comparable rows + 1 excluded row (`valsartan_smarts`); the second excluded task (`sitagliptin_mpo`) was pre-excluded before the sweep and never banked. The honest framing (matching the shipped README) is **23 denominator, 21 comparable, 21/21 beat-or-matched, 2 excluded-for-cause, decisive on 9, bar ≥6**. `verify_against_report()` cross-checks the derivable subset (comparable=21) against the JSON without coupling import to file IO. Not yet consumed by README/manifest — that wiring lands in 07-06/07-08; the 07-01 deliverable is the module + the "never 21/23" test.

- **`RunSnapshot.mode` / `RunListItem.mode` are REQUIRED (no default).** A dangerous silent default would be "benchmark" (it shows a baseline). Making mode required means any construction site that forgets it fails loudly. Mode is server-derived via `derive_mode()`, never client-set. Resume threads `mode=row.mode` so a resumed run keeps its gate.

- **Local Postgres schema drift gotcha.** `init_schema` is `create_all` (no ALTER); the shared dev DB (571 runs) had a stale `runs` table. The dev DB is Alembic-managed (stamped `f4251d568ae6`), so `alembic upgrade head` applied `f8342ecfc066` non-destructively — backfilled all 571 rows to `mode="benchmark"`. CI uses a fresh Postgres, so the migration drift test (`test_migrations.py`) passes there by construction; locally it passed after the upgrade.

- Gate: mypy clean · ruff clean · 325 backend tests · web typecheck + ESLint clean · 38 vitest · axe 10/10 (amber exploratory badge exercised on /runs·/overview·/compare in light+dark, clears AA).
