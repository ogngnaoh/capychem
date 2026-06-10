# Slice 2 — `01-local-loop`

> **Status: shipped (2026-06-11).** Frozen — see `handoff.md` for live status.

## Goal

A thin, end-to-end molecular-optimization loop — propose (Graph-GA over the harness bridge) → validate (modern RDKit) → score → persist → stop — runnable from a local CLI (`capychem-run`) on the QED task, budget-terminated, persisted to Postgres, and traced to Langfuse (no-op without keys).

## Plan (files touched)

Harness (isolated Python 3.10 env — never imported by modern code):
- `harness/capychem_harness/graph_ga/{__init__,crossover,mutate}.py` — Jensen GB-GA operators **vendored verbatim** from mol_opt (no PyTorch); `mutate.py`'s sibling import made package-relative.
- `harness/capychem_harness/data/starting_pop.smi` — ~200 ZINC-derived drug-like SMILES (public, attributed).
- `harness/capychem_harness/propose.py` — Graph-GA reproduce step (scored population → offspring + parent indices) over the subprocess+JSON bridge.
- `harness/pyproject.toml` — declare `numpy`.

Modern (`packages/core/capychem/`):
- `oracle.py` — `Offspring` dataclass + `propose_offspring()` bridge client (mirrors `score_smiles`).
- `validate.py` — RDKit canonicalize + drop-invalid + intra-batch dedup (FR-004).
- `db/{__init__,models,session}.py` — async SQLAlchemy 2.0 models (Run/Generation/Candidate/OracleCall) + engine/sessionmaker + `create_all` bootstrap.
- `loop/{__init__,state,logic,trace,graph}.py` — LoopState/Scored, pure decision helpers, Langfuse span helpers (no-op fallback), and the five-node LangGraph wiring.
- `cli.py` — `capychem-run` console-script driver.

Config / infra:
- `packages/core/pyproject.toml` — loop deps + `[project.scripts]`.
- root `pyproject.toml` — `rdkit.*` mypy override (broken 2026.3 stubs); `pytest-asyncio` + `asyncio_mode="auto"`.
- `.env.example` — `CAPYCHEM_DATABASE_URL` (asyncpg driver).
- `scripts/smoke.sh` — loop e2e check (now 9/9).

Tests (`packages/core/tests/`): `test_propose_bridge.py`, `test_validate.py`, `test_loop_logic.py`, `test_trace.py`, `test_cli_e2e.py` (22 tests total, real harness + Postgres).

## Tasks

- [x] 1. Dependencies (modern + harness numpy)
- [x] 2. Vendor Jensen Graph-GA operators (no torch)
- [x] 3. Vendor starting population
- [x] 4. Harness `propose.py` (reproduce step)
- [x] 5. Modern `propose_offspring()` bridge client
- [x] 6. Proposer determinism test (real harness)
- [x] 7. `validate.py` RDKit gate (TDD)
- [x] 8. Async SQLAlchemy models
- [x] 9. Async engine + session + bootstrap
- [x] 10. Loop state + pure logic helpers (TDD)
- [x] 11. Langfuse trace helpers, no-op fallback (TDD)
- [x] 12. LangGraph loop wiring (five nodes)
- [x] 13. `capychem-run` CLI
- [x] 14. End-to-end CLI test (real harness QED + Postgres)
- [x] 15. Smoke-script loop check
- [x] 16. Final gate + ship docs

## Notes (decisions, gotchas, deferrals)

**In-session decisions / corrections:**
- `propose.py` parent selection uses `np.random.choice(..., replace=True)` — **intentional**; self-pairing is permitted in the Jensen/mol_opt reference (`reproduce` draws two independent `random.choice`), so this is faithful, not a bug.
- rdkit 2026.3's `rdkit-stubs` has a `.pyi` syntax error that halts mypy once rdkit is imported → a scoped `[[tool.mypy.overrides]] module = "rdkit.*"` with `follow_imports="skip"` + `follow_imports_for_stubs=true` skips the broken stubs (rdkit → `Any`; one `cast(str, …)` in `validate.canonicalize`).
- `loop/trace.py` `span()` had a latent bug (the success `yield` sat inside the `try/except`, so a with-body exception triggered a second yield → masking `RuntimeError`). Fixed: yield moved to its own `try/finally`; enabled-path regression test added.
- langgraph 1.2.4's `CompiledStateGraph`/`StateGraph` take 4 type params → annotated `[Any, Any, Any, Any]` (loosely-typed builder surface).

**Deferred (out of scope this slice):**
- **Plateau detection (FR-003)** — `plateau_window` is configured + persisted but NOT enforced; the loop stops on budget exhaustion, max-generations, or zero forward progress only.
- **LLM proposer + invalid→fallback (FR-005)** — Graph-GA is the sole proposer; no LLM. → milestone 02.
- **Analyzer step (FR-007)** — → milestone 03.
- **REST / WebSocket / web UI (FR-009..FR-014)** — → slice 3 (`02-web-surface`).
- **Authoritative PMO AUC** — `summary.auc_curve` is the running top-10 mean, NOT the canonical AUC-of-top-10-vs-oracle-calls (that lives in `packages/core/eval`, a later milestone). Do not treat it as the G1 number.
- **Cross-generation dedup / memoization** — only intra-batch dedup in `validate_batch`.
- **Operator seed-population override** — gen 0 uses the vendored `starting_pop.smi` only.
- **SPEC §6.2 deferrals** — RunCost + AnalyzerHypothesis tables; `config_json`, `selfies`, `oracle_call_id`, `events_json`, `analyzer_hypothesis_id` columns; the `(task,status,started_at)` list-view index. Alembic (using `create_all` for now).
- **Full `mol_opt` + `BaseOptimizer` baseline reproduction** — this slice vendored only the two Jensen operators (no PyTorch); the full harness baseline stays in milestone 01.
- **Langfuse enabled-path nested trace** — not manually verified this session (no `LANGFUSE_*` keys set); the no-op path is CI-covered. Manual run→gen→node trace check pending once keys are configured.
