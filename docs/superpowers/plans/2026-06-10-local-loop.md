# Local Loop (Slice 2 `01-local-loop`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a thin end-to-end molecular-optimization loop — propose (Graph-GA over the harness bridge) → validate (modern RDKit) → score → persist → stop — runnable from a local CLI on the QED task, budget-terminated, persisted to Postgres, traced to Langfuse.

**Architecture:** A new harness entry `propose.py` runs one Jensen Graph-GA *reproduce* step (vendored `crossover.py`/`mutate.py`, no PyTorch) and returns offspring SMILES with parent indices. Modern code reaches it via the existing subprocess+JSON bridge pattern (mirrors `score.py`/`oracle.py`). A LangGraph state machine drives the five nodes; async SQLAlchemy 2.0 (asyncpg) persists Run/Generation/Candidate/OracleCall; Langfuse spans nest run→generation→node (no-op when keys absent). A `capychem-run` console script wraps the loop in `asyncio.run`.

**Tech Stack:** Python 3.12 (modern) + Python 3.10 (harness, isolated). RDKit, numpy (harness). LangGraph, Langfuse, SQLAlchemy 2.0 `[asyncio]`, asyncpg, RDKit (modern). uv workspaces, pytest, mypy strict, ruff. Postgres 16 (Docker, `infra/compose.yml`).

**Design doc:** `docs/superpowers/specs/2026-06-08-local-loop-design.md` (approved). Read it before starting.

**Ground rules (from CLAUDE.md — do not violate):**
- NEVER `import` from `harness/` in `packages/` or `apps/`. The only crossing is subprocess+JSON via `packages/core/capychem/oracle.py`.
- Validate every SMILES via RDKit before persistence (FR-004).
- Every LangGraph node emits a Langfuse span ("no silent loop steps").
- `mypy -p capychem` strict + `ruff check packages apps/api` stay green on all new modern code.
- Commit frequently, one logical change per commit, on `main` (this is the main-flow branch for the slice; no worktree requested).
- Commit message trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

**Pre-flight:** Postgres must be up: `docker compose -f infra/compose.yml up -d`. Harness venv must exist: `test -x harness/.venv/bin/python` (built in slice 1).

---

## File Structure

Harness (Python 3.10, isolated — `harness/capychem_harness/`):
- `graph_ga/__init__.py` — package marker (harness-internal; not part of the modern `capychem` namespace).
- `graph_ga/crossover.py` — **vendored verbatim** Jensen GB-GA crossover (RDKit + numpy + random).
- `graph_ga/mutate.py` — **vendored verbatim** Jensen GB-GA mutation.
- `propose.py` — NEW bridge entry: scored population → ≤N offspring SMILES with parent indices.
- `data/starting_pop.smi` — vendored ZINC-derived starting population (~100–250 SMILES) + attribution header.

Modern (`packages/core/capychem/`):
- `oracle.py` — MODIFY: add `Offspring` dataclass + `propose_offspring()` client (mirrors `score_smiles`).
- `validate.py` — NEW: canonicalize, drop invalid + intra-batch duplicates (FR-004).
- `db/__init__.py`, `db/models.py`, `db/session.py` — NEW: async SQLAlchemy 2.0 models + engine/session.
- `loop/__init__.py`, `loop/state.py`, `loop/logic.py`, `loop/trace.py`, `loop/graph.py` — NEW: state, pure helpers, Langfuse helpers, LangGraph wiring.
- `cli.py` — NEW: `capychem-run` console script.

Config:
- `packages/core/pyproject.toml` — MODIFY: add deps + `[project.scripts]`.
- `harness/pyproject.toml` — MODIFY: declare `numpy`.
- `.env.example` — MODIFY: `CAPYCHEM_DATABASE_URL` (asyncpg driver).
- `scripts/smoke.sh` — MODIFY: add loop check.

Tests (`packages/core/tests/`):
- `test_validate.py`, `test_loop_logic.py` — pure unit tests (no DB, no harness).
- `test_propose_bridge.py` — integration: real harness propose determinism.
- `test_trace.py` — Langfuse no-op fallback.
- `test_cli_e2e.py` — integration: real harness QED + Postgres, full run.

---

## Task 1: Dependencies (modern deps + harness numpy)

**Files:**
- Modify: `packages/core/pyproject.toml`
- Modify: `harness/pyproject.toml:6-13`

- [ ] **Step 1: Add modern deps to `packages/core/pyproject.toml`**

Replace `dependencies = []` with (pin `rdkit` to the harness major.minor `2026.3.*` per the design — both envs canonicalize SMILES and must agree):

```toml
dependencies = [
    "rdkit==2026.3.*",
    "langgraph>=0.2",
    "langfuse>=2,<3",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
]
```

Also add the console script (used in Task 13 — add it now so the entry point exists):

```toml
[project.scripts]
capychem-run = "capychem.cli:main"
```

- [ ] **Step 2: Declare numpy in `harness/pyproject.toml`**

In the `dependencies` list (after `scipy`), add `numpy` (already present transitively via PyTDC; declared for hygiene — the Graph-GA operators use it):

```toml
dependencies = [
    "pytdc==0.3.6",
    "rdkit",
    "requests",
    "networkx",
    "scipy",
    "numpy",
]
```

- [ ] **Step 3: Sync both envs**

Run: `uv sync && uv sync --project harness`
Expected: both resolve without error. Confirm the modern rdkit matches the harness line:
Run: `uv run python -c "import rdkit; print(rdkit.__version__)"` → expect `2026.03.*`.
Run: `harness/.venv/bin/python -c "import rdkit, numpy; print(rdkit.__version__, numpy.__version__)"` → expect `2026.03.2` (or close) + a numpy version.

If the pin `2026.3.*` cannot resolve in the modern env (PyPI yanked / unavailable), pin instead to the exact harness version printed by the second command, and note the deviation in the commit.

- [ ] **Step 4: Commit**

```bash
git add packages/core/pyproject.toml harness/pyproject.toml uv.lock harness/uv.lock
git commit -m "build(slice2): add loop deps (rdkit/langgraph/langfuse/sqlalchemy/asyncpg) + harness numpy

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: Vendor the Jensen Graph-GA operators into the harness

These are **third-party files copied verbatim** — do not hand-write them. Source: the `mol_opt` repo (`wenhao-gao/mol_opt`), path `main/graph_ga/`, which itself vendors them from Jan Jensen's GB-GA (`jensengroup/GB_GA`, MIT-spirit, public). Either repo is an acceptable source; prefer `mol_opt`'s copies for milestone-01 alignment.

**Files:**
- Create: `harness/capychem_harness/graph_ga/__init__.py`
- Create: `harness/capychem_harness/graph_ga/crossover.py`
- Create: `harness/capychem_harness/graph_ga/mutate.py`

- [ ] **Step 1: Create the package marker**

`harness/capychem_harness/graph_ga/__init__.py`:

```python
"""Vendored Jensen GB-GA operators (RDKit + numpy, no PyTorch).

Copied verbatim from mol_opt (wenhao-gao/mol_opt, main/graph_ga/), which vendors
them from jensengroup/GB_GA. Harness-internal only — modern code reaches Graph-GA
through ``propose.py`` via subprocess, never by import.
"""
```

- [ ] **Step 2: Vendor `crossover.py` and `mutate.py` verbatim**

Copy `crossover.py` and `mutate.py` from `mol_opt/main/graph_ga/` into `harness/capychem_harness/graph_ga/`, unmodified except for a one-line provenance comment at the top of each:

```python
# Vendored verbatim from mol_opt (main/graph_ga/), originally jensengroup/GB_GA. Unmodified.
```

These modules expose, respectively, `crossover(parent_A, parent_B) -> rdkit.Chem.Mol | None` and `mutate(mol, mutation_rate) -> rdkit.Chem.Mol | None`. `propose.py` (Task 4) depends on exactly those two names/signatures.

- [ ] **Step 3: Verify no PyTorch and the expected signatures exist**

Run:
```bash
grep -rEn 'import torch|from torch' harness/capychem_harness/graph_ga/ ; echo "torch-hits: $?"
grep -n 'def crossover' harness/capychem_harness/graph_ga/crossover.py
grep -n 'def mutate'   harness/capychem_harness/graph_ga/mutate.py
```
Expected: the torch grep prints nothing (exit status line shows `1` = no matches); `def crossover(` and `def mutate(` are found. If torch is imported, you copied the wrong file (a neural method) — re-fetch only `crossover.py` and `mutate.py` from `main/graph_ga/`.

- [ ] **Step 4: Verify the operators import and run under the harness interpreter**

Run (`PYTHONPATH=harness` makes the `capychem_harness` package importable since it is not installed):
```bash
PYTHONPATH=harness harness/.venv/bin/python - <<'PY'
import random; random.seed(0)
import numpy as np; np.random.seed(0)
from rdkit import Chem
from capychem_harness.graph_ga import crossover as co, mutate as mu
a = Chem.MolFromSmiles("CCO"); b = Chem.MolFromSmiles("c1ccccc1")
child = co.crossover(a, b)
print("crossover:", None if child is None else Chem.MolToSmiles(child))
if child is not None:
    m = mu.mutate(child, 0.5)
    print("mutate:", None if m is None else Chem.MolToSmiles(m))
print("ok")
PY
```
Expected: prints `crossover: ...`, `mutate: ...` (either may be `None` — crossover can fail validity checks; rerun if both None), and `ok`. This confirms the vendored files load and the signatures match. (Run from the repo root; the harness package is importable because the script runs under the harness interpreter, which is allowed — this is the harness testing itself, not modern code importing the harness.)

- [ ] **Step 5: Commit**

```bash
git add harness/capychem_harness/graph_ga/
git commit -m "feat(slice2): vendor Jensen Graph-GA crossover/mutate into harness (no torch)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: Vendor the starting population

**Files:**
- Create: `harness/capychem_harness/data/starting_pop.smi`

- [ ] **Step 1: Obtain ~100–250 drug-like SMILES**

Source from `mol_opt`'s Graph-GA starting set (ZINC-derived, public). If you have `mol_opt` checked out, take the first ~200 lines of its starting-population file (e.g. `main/graph_ga/` data or the repo's `data/zinc251.txt`-style file). Otherwise use any public ZINC drug-like sample of ~200 SMILES. One SMILES per line.

- [ ] **Step 2: Write the file with an attribution header**

`harness/capychem_harness/data/starting_pop.smi` — first lines are comments (PRD N3 / SPEC public-data requirement), then one SMILES per line:

```
# CapyChem starting population for Graph-GA (slice 2).
# Source: ZINC-derived drug-like sample, via mol_opt (wenhao-gao/mol_opt). Public.
# One SMILES per line. Lines starting with '#' are comments.
CCO
c1ccccc1
... (≈200 SMILES total)
```

- [ ] **Step 3: Verify count and validity under the harness RDKit**

Run:
```bash
harness/.venv/bin/python - <<'PY'
from rdkit import Chem
from pathlib import Path
p = Path("harness/capychem_harness/data/starting_pop.smi")
smis = [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")]
valid = [s for s in smis if Chem.MolFromSmiles(s) is not None]
print(f"total={len(smis)} valid={len(valid)}")
assert 100 <= len(smis) <= 300, "expected ~100-250 SMILES"
assert len(valid) == len(smis), "all starting SMILES must be RDKit-valid"
print("ok")
PY
```
Expected: `total=~200 valid=~200` and `ok`.

- [ ] **Step 4: Commit**

```bash
git add harness/capychem_harness/data/starting_pop.smi
git commit -m "feat(slice2): vendor ZINC-derived Graph-GA starting population

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: Harness `propose.py` (the Graph-GA reproduce step)

**Files:**
- Create: `harness/capychem_harness/propose.py`

- [ ] **Step 1: Write `propose.py`** (mirrors `score.py`'s stdout-redirect + `_emit`/`_err` discipline)

```python
"""Harness-side Graph-GA proposer (runs under the pinned Python 3.10 venv).

Reads a scored population on stdin, runs ONE Jensen Graph-GA reproduce step
(fitness-weighted parent selection -> crossover -> probabilistic mutate), and
writes the offspring (with parent provenance) as a single JSON line on stdout.
Reached only via subprocess from modern code — never imported.

Request  (stdin) : {"population": [{"smiles": "...", "score": 0.61}, ...],
                    "n_offspring": 32, "mutation_rate": 0.01, "seed": 42}
Response (stdout): {"offspring": [{"smiles": "...", "parents": [i, j]}, ...],
                    "error": null}

`parents` are indices into the request `population` array (the two crossover
parents). A generation may return FEWER than n_offspring offspring: crossover can
fail RDKit ring/validity checks and yield nothing for a slot. On failure:
exit code 1 and {"offspring": [], "error": "<message>"}.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

# Running a script BY PATH puts the script's own dir (…/capychem_harness/) on
# sys.path[0], not the harness root — so `capychem_harness` is not importable.
# Add the harness root (parents[1] of this file = harness/) so the package import
# below resolves. The harness is package=false / not installed, so this is needed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Same discipline as score.py: capture the real stdout, redirect Python-level
# stdout to stderr so RDKit/numpy chatter cannot corrupt the JSON response.
_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr


def _emit(payload: dict, code: int = 0) -> None:
    json.dump(payload, _REAL_STDOUT)
    _REAL_STDOUT.write("\n")
    _REAL_STDOUT.flush()
    sys.exit(code)


def _err(msg: str) -> None:
    _emit({"offspring": [], "error": msg}, code=1)


def main() -> None:
    try:
        req = json.loads(sys.stdin.read())
        population = list(req["population"])
        n_offspring = int(req["n_offspring"])
        mutation_rate = float(req["mutation_rate"])
        seed = int(req["seed"])
    except (ValueError, KeyError, TypeError) as exc:
        _err(f"Send JSON with 'population', 'n_offspring', 'mutation_rate', 'seed': {exc}")
        return

    try:
        import numpy as np
        from rdkit import Chem

        from capychem_harness.graph_ga import crossover as co
        from capychem_harness.graph_ga import mutate as mu
    except Exception as exc:  # noqa: BLE001 - surface any import failure to caller
        _err(f"Install numpy + rdkit in the harness env (uv sync in harness/): {exc}")
        return

    # Deterministic per the request seed (modern side passes base_seed + gen_index).
    random.seed(seed)
    np.random.seed(seed)

    # Parse parents to Mols; keep the original population index for provenance.
    mols = []
    weights = []
    indices = []
    for i, member in enumerate(population):
        mol = Chem.MolFromSmiles(member["smiles"])
        if mol is None:
            continue
        mols.append(mol)
        weights.append(max(float(member["score"]), 0.0))
        indices.append(i)

    if len(mols) < 2:
        _err("Need at least two valid parents to run crossover")
        return

    # Fitness-weighted selection probabilities (Jensen make_mating_pool).
    total = sum(weights)
    probs = [w / total for w in weights] if total > 0 else [1.0 / len(weights)] * len(weights)

    offspring = []
    for _ in range(n_offspring):
        a, b = (int(x) for x in np.random.choice(len(mols), size=2, p=probs, replace=True))
        child = co.crossover(mols[a], mols[b])
        if child is None:
            continue
        child = mu.mutate(child, mutation_rate)
        if child is None:
            continue
        smi = Chem.MolToSmiles(child)
        if not smi:
            continue
        offspring.append({"smiles": smi, "parents": [indices[a], indices[b]]})

    _emit({"offspring": offspring, "error": None})


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke the proposer directly under the harness interpreter**

Run:
```bash
echo '{"population":[{"smiles":"CCO","score":0.4},{"smiles":"c1ccccc1","score":0.6},{"smiles":"CCN","score":0.5}],"n_offspring":8,"mutation_rate":0.01,"seed":42}' \
  | harness/.venv/bin/python harness/capychem_harness/propose.py
```
Expected: a single JSON line `{"offspring": [{"smiles": "...", "parents": [..]}, ...], "error": null}` with 0–8 offspring, each `parents` a 2-element list of indices in `{0,1,2}`. No stray chatter on stdout.

- [ ] **Step 3: Commit**

```bash
git add harness/capychem_harness/propose.py
git commit -m "feat(slice2): harness propose.py — Graph-GA reproduce step over the bridge

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 5: Modern `propose_offspring()` bridge client

**Files:**
- Modify: `packages/core/capychem/oracle.py`

- [ ] **Step 1: Add the `Offspring` dataclass and `_PROPOSER` path**

In `oracle.py`, after the `OracleResult` dataclass (around line 38), add:

```python
@dataclass(frozen=True)
class Offspring:
    """One Graph-GA offspring with the indices of its two crossover parents.

    ``parents`` indexes into the population list passed to ``propose_offspring``.
    """

    smiles: str
    parents: tuple[int, int]
```

After the `_SCORER` definition (around line 23), add:

```python
_PROPOSER = _REPO_ROOT / "harness" / "capychem_harness" / "propose.py"
```

- [ ] **Step 2: Add the `propose_offspring()` client** (mirrors `score_smiles`)

Append to `oracle.py`:

```python
def propose_offspring(
    population: list[tuple[str, float]],
    n_offspring: int,
    *,
    mutation_rate: float,
    seed: int,
    timeout_s: float = 120.0,
) -> list[Offspring]:
    """Run one Graph-GA reproduce step via the isolated harness subprocess.

    ``population`` is a list of (smiles, score) pairs. Returns offspring SMILES,
    each with the indices (into ``population``) of its two crossover parents. May
    return fewer than ``n_offspring`` (crossover can fail validity checks).
    Raises ``HarnessError`` if the harness env is missing, the subprocess fails,
    or the response is malformed.
    """
    python = _harness_python()
    if not python.exists():
        raise HarnessError(
            f"Build the harness env first (`uv sync` in harness/); "
            f"interpreter not found at {python}"
        )

    request = json.dumps(
        {
            "population": [{"smiles": s, "score": sc} for s, sc in population],
            "n_offspring": n_offspring,
            "mutation_rate": mutation_rate,
            "seed": seed,
        }
    )
    try:
        proc = subprocess.run(
            [str(python), str(_PROPOSER)],
            input=request,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(f"Harness proposal timed out after {timeout_s}s") from exc

    payload = _parse_last_json_line(proc.stdout)
    if payload is None:
        raise HarnessError(
            f"Harness returned no JSON (exit {proc.returncode}). "
            f"stderr tail: {proc.stderr[-500:]}"
        )
    if payload.get("error"):
        raise HarnessError(str(payload["error"]))

    return [
        Offspring(smiles=row["smiles"], parents=(row["parents"][0], row["parents"][1]))
        for row in payload["offspring"]
    ]
```

- [ ] **Step 3: Typecheck + lint**

Run: `uv run mypy -p capychem && uv run ruff check packages`
Expected: clean (no errors). (No test yet — Task 6 adds the integration test.)

- [ ] **Step 4: Commit**

```bash
git add packages/core/capychem/oracle.py
git commit -m "feat(slice2): modern propose_offspring() bridge client + Offspring dataclass

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 6: Proposer determinism test (real harness, TDD)

**Files:**
- Test: `packages/core/tests/test_propose_bridge.py`

- [ ] **Step 1: Write the failing test**

```python
"""Integration test of the Graph-GA proposer over the real harness bridge.

Exercises the real harness venv (Python 3.10) via subprocess — no mocking.
Proves determinism (G6, slice-local): same seed -> identical offspring + parents.
"""

from __future__ import annotations

from capychem.oracle import Offspring, propose_offspring

_POP = [("CCO", 0.40), ("c1ccccc1", 0.60), ("CCN", 0.50), ("CCOC", 0.55)]


def test_propose_returns_offspring_with_parent_indices() -> None:
    out = propose_offspring(_POP, n_offspring=8, mutation_rate=0.01, seed=42)
    assert all(isinstance(o, Offspring) for o in out)
    assert len(out) <= 8  # may be fewer: crossover can fail
    for o in out:
        assert isinstance(o.smiles, str) and o.smiles
        i, j = o.parents
        assert 0 <= i < len(_POP) and 0 <= j < len(_POP)


def test_propose_is_deterministic_for_same_seed() -> None:
    a = propose_offspring(_POP, n_offspring=8, mutation_rate=0.01, seed=42)
    b = propose_offspring(_POP, n_offspring=8, mutation_rate=0.01, seed=42)
    assert [(o.smiles, o.parents) for o in a] == [(o.smiles, o.parents) for o in b]
```

- [ ] **Step 2: Run to verify it passes** (the implementation already exists from Tasks 4–5)

Run: `uv run pytest packages/core/tests/test_propose_bridge.py -v`
Expected: PASS. If `test_propose_is_deterministic_for_same_seed` fails, the operators or `propose.py` are reading an unseeded RNG — confirm `propose.py` seeds both `random` and `np.random`, and that the vendored operators use only those two RNGs (grep the operators for `random.` / `np.random` / `numpy.random`).

- [ ] **Step 3: Commit**

```bash
git add packages/core/tests/test_propose_bridge.py
git commit -m "test(slice2): proposer determinism + parent-index provenance over the bridge

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 7: `validate.py` (modern RDKit gate) — TDD

**Files:**
- Create: `packages/core/capychem/validate.py`
- Test: `packages/core/tests/test_validate.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from capychem.validate import ValidCandidate, canonicalize, validate_batch


def test_canonicalize_returns_canonical_form() -> None:
    # Two spellings of ethanol canonicalize to the same string.
    assert canonicalize("OCC") == canonicalize("CCO")


def test_canonicalize_returns_none_for_invalid() -> None:
    assert canonicalize("not_a_smiles") is None


def test_validate_batch_drops_invalid_and_dedups_keeping_first_provenance() -> None:
    batch = [
        ("CCO", (0, 1)),
        ("OCC", (2, 3)),          # duplicate of CCO by canonical form
        ("not_a_smiles", (4, 5)), # invalid -> dropped
        ("c1ccccc1", None),       # gen-0 style, no parents
    ]
    out = validate_batch(batch)
    assert [c.smiles for c in out] == [canonicalize("CCO"), canonicalize("c1ccccc1")]
    assert out[0].parents == (0, 1)  # first occurrence wins
    assert out[1].parents is None


def test_validate_batch_empty_on_all_invalid() -> None:
    assert validate_batch([("xxx", None), ("yyy", None)]) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capychem.validate'`.

- [ ] **Step 3: Write `validate.py`**

```python
"""Modern-RDKit SMILES validation + canonicalization (Python 3.12 side).

Runs before any oracle call: invalid SMILES are dropped and intra-batch
duplicates collapsed by canonical form, so the budget is never spent on junk
(FR-004). The harness scores; this gate decides what reaches it.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem, RDLogger

# Silence per-molecule parse warnings; invalidity is signalled by a None mol.
RDLogger.DisableLog("rdApp.*")


@dataclass(frozen=True)
class ValidCandidate:
    """A canonicalized, unique candidate that survived validation.

    ``parents`` carries the proposer's provenance forward (None at gen 0).
    """

    smiles: str  # canonical SMILES
    parents: tuple[int, int] | None


def canonicalize(smiles: str) -> str | None:
    """Return canonical SMILES, or None if RDKit cannot parse it."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)


def validate_batch(
    candidates: list[tuple[str, tuple[int, int] | None]],
) -> list[ValidCandidate]:
    """Canonicalize, drop invalid, collapse intra-batch duplicates.

    ``candidates`` is a list of (raw_smiles, parents) pairs. The first occurrence
    of each canonical form wins (keeping its provenance). Input order is
    preserved — deterministic for G6.
    """
    seen: set[str] = set()
    out: list[ValidCandidate] = []
    for raw, parents in candidates:
        canon = canonicalize(raw)
        if canon is None or canon in seen:
            continue
        seen.add(canon)
        out.append(ValidCandidate(smiles=canon, parents=parents))
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_validate.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/validate.py packages/core/tests/test_validate.py
git commit -m "feat(slice2): modern RDKit validate+canonicalize gate (FR-004)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 8: Database models (async SQLAlchemy 2.0)

**Files:**
- Create: `packages/core/capychem/db/__init__.py`
- Create: `packages/core/capychem/db/models.py`

- [ ] **Step 1: Create the sub-package marker**

`packages/core/capychem/db/__init__.py`:

```python
"""Async SQLAlchemy 2.0 persistence for CapyChem run state."""
```

(`capychem` itself stays a PEP 420 namespace with no `__init__.py`; sub-packages like `db` may carry their own — see design doc.)

- [ ] **Step 2: Write `db/models.py`**

```python
"""Async SQLAlchemy 2.0 models for CapyChem run state (SPEC §6.2, minus RunCost).

Four entities for slice 2: Run, Generation, Candidate, OracleCall. RunCost +
AnalyzerHypothesis arrive in later slices. Schema is bootstrapped via
metadata.create_all (db/session.py); Alembic lands with the first additive change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(64))
    budget: Mapped[int]
    mutation_strategy: Mapped[str] = mapped_column(String(32), default="graph_ga")
    plateau_window: Mapped[int]
    pop_size: Mapped[int]
    offspring: Mapped[int]
    mutation_rate: Mapped[float]
    seed: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(default=None)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


class Generation(Base):
    __tablename__ = "generations"
    __table_args__ = (Index("ix_generation_run_index", "run_id", "index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    index: Mapped[int]
    proposer_used: Mapped[str] = mapped_column(String(16))  # "starting" | "graph_ga"
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(default=None)


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[int] = mapped_column(
        ForeignKey("generations.id", ondelete="CASCADE")
    )
    smiles: Mapped[str] = mapped_column(String(512))
    parent_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), default=None
    )
    proposer: Mapped[str] = mapped_column(String(16))  # "starting" | "graph_ga"
    valid: Mapped[bool] = mapped_column(default=True)
    score: Mapped[float | None] = mapped_column(default=None)


class OracleCall(Base):
    __tablename__ = "oracle_calls"
    __table_args__ = (Index("ix_oraclecall_run_score", "run_id", "score"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE")
    )
    task: Mapped[str] = mapped_column(String(64))
    score: Mapped[float]
    wall_ms: Mapped[int]
    compute_cost_usd: Mapped[float] = mapped_column(default=0.0)  # 0 for local oracle
```

Note on the `(run_id, score DESC)` index: SQLAlchemy's plain `Index("...", "run_id", "score")` creates an ascending index; Postgres can scan it backwards for top-K, so ascending is sufficient here. (A true `DESC` index would use `OracleCall.score.desc()` and requires importing the column object; not needed at this volume.)

- [ ] **Step 3: Typecheck + lint**

Run: `uv run mypy -p capychem && uv run ruff check packages`
Expected: clean. (Persistence behavior is exercised by the e2e test in Task 14.)

- [ ] **Step 4: Commit**

```bash
git add packages/core/capychem/db/__init__.py packages/core/capychem/db/models.py
git commit -m "feat(slice2): async SQLAlchemy models — Run/Generation/Candidate/OracleCall

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 9: Async engine + session + schema bootstrap

**Files:**
- Create: `packages/core/capychem/db/session.py`
- Modify: `.env.example`

- [ ] **Step 1: Write `db/session.py`**

```python
"""Async engine, sessionmaker, and first-connect schema bootstrap.

metadata.create_all is fine while the greenfield schema churns (slice 2); Alembic
arrives with the first additive change (slice 3/4). Reads CAPYCHEM_DATABASE_URL
(asyncpg driver). Dev resets are drop/recreate.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from capychem.db.models import Base

_DEFAULT_URL = "postgresql+asyncpg://capychem:capychem@localhost:5432/capychem"


def database_url() -> str:
    return os.environ.get("CAPYCHEM_DATABASE_URL", _DEFAULT_URL)


def make_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(url or database_url(), future=True)


async def init_schema(engine: AsyncEngine) -> None:
    """Create all tables if they do not exist (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

- [ ] **Step 2: Update `.env.example`** — change ONLY the `DATABASE_URL=...` line to the asyncpg-driver var the code reads (leave `CAPYCHEM_HARNESS_PYTHON`, `NEXT_PUBLIC_API_URL`, and the `POSTGRES_*` lines untouched). The Postgres block becomes:

```
# Postgres (infra/compose.yml) — run state. Local dev credentials.
POSTGRES_USER=capychem
POSTGRES_PASSWORD=capychem
POSTGRES_DB=capychem
CAPYCHEM_DATABASE_URL=postgresql+asyncpg://capychem:capychem@localhost:5432/capychem
```

- [ ] **Step 3: Verify schema bootstrap against the running Postgres**

Run (Postgres must be up — `docker compose -f infra/compose.yml up -d`):
```bash
uv run python - <<'PY'
import asyncio
from capychem.db.session import make_engine, init_schema

async def main():
    eng = make_engine()
    await init_schema(eng)
    async with eng.connect() as conn:
        from sqlalchemy import text
        rows = await conn.execute(text(
            "select tablename from pg_tables where schemaname='public' order by tablename"))
        print(sorted(r[0] for r in rows))
    await eng.dispose()

asyncio.run(main())
PY
```
Expected: prints a list including `candidates`, `generations`, `oracle_calls`, `runs`.

- [ ] **Step 4: Commit**

```bash
git add packages/core/capychem/db/session.py .env.example
git commit -m "feat(slice2): async engine + session + create_all bootstrap; CAPYCHEM_DATABASE_URL

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 10: Loop state + pure logic helpers — TDD

Factor all branch-free decision logic into pure functions so they unit-test without a DB or harness. The LangGraph nodes (Task 12) call these.

**Files:**
- Create: `packages/core/capychem/loop/__init__.py`
- Create: `packages/core/capychem/loop/state.py`
- Create: `packages/core/capychem/loop/logic.py`
- Test: `packages/core/tests/test_loop_logic.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from capychem.loop.logic import (
    build_summary,
    merge_and_truncate,
    stop_reason,
    trim_to_budget,
)
from capychem.loop.state import Scored


def s(smiles: str, score: float, cid: int | None = None) -> Scored:
    return Scored(smiles=smiles, score=score, candidate_id=cid)


def test_trim_to_budget_caps_batch_to_remaining() -> None:
    items = ["a", "b", "c", "d"]
    assert trim_to_budget(items, budget=10, calls_used=8) == ["a", "b"]
    assert trim_to_budget(items, budget=10, calls_used=10) == []
    assert trim_to_budget(items, budget=10, calls_used=2) == items


def test_merge_and_truncate_keeps_top_pop_size_with_canonical_tiebreak() -> None:
    pop = [s("CCO", 0.5, 1), s("CCN", 0.5, 2)]
    batch = [s("c1ccccc1", 0.9, 3), s("CCC", 0.5, 4)]
    out = merge_and_truncate(pop, batch, pop_size=2)
    assert [m.smiles for m in out] == ["c1ccccc1", "CCC"]  # 0.9 first; ties broken by smiles


def test_stop_reason_budget_exhausted() -> None:
    assert stop_reason(calls_used=100, budget=100, gen_index=2,
                       max_generations=100, made_progress=True) == "exhausted"


def test_stop_reason_max_generations() -> None:
    assert stop_reason(calls_used=10, budget=100, gen_index=100,
                       max_generations=100, made_progress=True) == "max_generations"


def test_stop_reason_zero_progress() -> None:
    assert stop_reason(calls_used=10, budget=100, gen_index=3,
                       max_generations=100, made_progress=False) == "no_progress"


def test_stop_reason_continue() -> None:
    assert stop_reason(calls_used=10, budget=100, gen_index=3,
                       max_generations=100, made_progress=True) is None


def test_build_summary_shape() -> None:
    pop = [s("c1ccccc1", 0.9, 3), s("CCO", 0.5, 1)]
    curve = [(20, 0.5), (30, 0.7)]
    summary = build_summary(pop, curve, generations=3, oracle_calls=30, top_k=10)
    assert summary["top_k"][0] == {"smiles": "c1ccccc1", "score": 0.9}
    assert summary["auc_curve"] == [
        {"oracle_calls": 20, "top10_mean": 0.5},
        {"oracle_calls": 30, "top10_mean": 0.7},
    ]
    assert summary["generations"] == 3 and summary["oracle_calls"] == 30
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_loop_logic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capychem.loop'`.

- [ ] **Step 3: Write `loop/__init__.py`, `loop/state.py`, `loop/logic.py`**

`packages/core/capychem/loop/__init__.py`:

```python
"""LangGraph optimization loop: propose -> validate -> score -> persist -> stop."""
```

`packages/core/capychem/loop/state.py`:

```python
"""Loop state for the LangGraph runtime.

``Scored`` carries a candidate's DB id so offspring can resolve their
``parent_candidate_id`` from the survivor pool. ``LoopState`` is a TypedDict
(LangGraph merges node return dicts into it); it threads Langfuse parent span ids
explicitly so node spans nest across async boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from capychem.validate import ValidCandidate


@dataclass(frozen=True)
class Scored:
    smiles: str  # canonical
    score: float
    candidate_id: int | None = None  # DB id once persisted; enables parent provenance


class LoopState(TypedDict, total=False):
    # config / identity
    run_id: int
    task: str
    budget: int
    seed: int
    pop_size: int
    offspring: int
    mutation_rate: float
    plateau_window: int
    max_generations: int
    # progress
    calls_used: int
    gen_index: int
    population: list[Scored]  # survivor pool, kept at pop_size
    # langfuse span ids threaded for nesting across async nodes
    run_span_id: str | None
    gen_span_id: str | None
    # transient per-iteration carriers (read across nodes — MUST be declared, or
    # mypy errors `TypedDict has no key`; the leading underscore is just a naming
    # convention for "internal", it does not exempt them from declaration)
    proposed: list[tuple[str, tuple[int, int] | None]]
    validated: list[ValidCandidate]
    _proposer: str
    _scored: list[tuple[ValidCandidate, float]]
    _made_progress: bool
    auc_curve: list[tuple[int, float]]
    done: bool
    stop_reason: str | None
    summary: dict[str, Any] | None
```

`packages/core/capychem/loop/logic.py`:

```python
"""Pure decision helpers for the loop — no DB, no harness, no I/O.

Kept free of side effects so they unit-test in isolation and stay deterministic.
"""

from __future__ import annotations

from typing import Any, TypeVar

from capychem.loop.state import Scored

T = TypeVar("T")


def trim_to_budget(items: list[T], *, budget: int, calls_used: int) -> list[T]:
    """Cap a validated batch to the remaining budget so a generation never
    overshoots (FR-002)."""
    remaining = max(budget - calls_used, 0)
    return items[:remaining]


def _sort_key(m: Scored) -> tuple[float, str]:
    # Descending score; ascending canonical SMILES as a deterministic tiebreak (G6).
    return (-m.score, m.smiles)


def merge_and_truncate(
    population: list[Scored], batch: list[Scored], *, pop_size: int
) -> list[Scored]:
    """Merge offspring + survivors and keep the top ``pop_size`` by score, with a
    deterministic canonical-SMILES tiebreak."""
    merged = sorted([*population, *batch], key=_sort_key)
    return merged[:pop_size]


def stop_reason(
    *,
    calls_used: int,
    budget: int,
    gen_index: int,
    max_generations: int,
    made_progress: bool,
) -> str | None:
    """Return a termination reason, or None to continue.

    Priority: budget exhaustion (FR-002) > max-generations cap > zero forward
    progress (guards against an all-invalid / all-duplicate batch looping forever).
    """
    if calls_used >= budget:
        return "exhausted"
    if gen_index >= max_generations:
        return "max_generations"
    if not made_progress:
        return "no_progress"
    return None


def build_summary(
    population: list[Scored],
    auc_curve: list[tuple[int, float]],
    *,
    generations: int,
    oracle_calls: int,
    top_k: int = 10,
) -> dict[str, Any]:
    """Build the (un-authoritative) summary_json. The auc_curve here is the
    running top-10-mean; the canonical AUC lives in packages/core/eval (later
    milestone) — do not treat this as the G1 number."""
    top = sorted(population, key=_sort_key)[:top_k]
    return {
        "top_k": [{"smiles": m.smiles, "score": m.score} for m in top],
        "auc_curve": [{"oracle_calls": c, "top10_mean": v} for c, v in auc_curve],
        "generations": generations,
        "oracle_calls": oracle_calls,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_loop_logic.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Typecheck + commit**

Run: `uv run mypy -p capychem && uv run ruff check packages`
Expected: clean.

```bash
git add packages/core/capychem/loop/__init__.py packages/core/capychem/loop/state.py \
        packages/core/capychem/loop/logic.py packages/core/tests/test_loop_logic.py
git commit -m "feat(slice2): loop state + pure logic helpers (budget trim, truncate, stop, summary)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 11: Langfuse trace helpers (no-op fallback) — TDD

**Files:**
- Create: `packages/core/capychem/loop/trace.py`
- Test: `packages/core/tests/test_trace.py`

- [ ] **Step 1: Write the failing test** (the critical contract is: NO Langfuse keys ⇒ no-ops, no exceptions, so CI never needs a running Langfuse)

```python
from __future__ import annotations

import contextlib

from capychem.loop import trace


def test_disabled_without_keys(monkeypatch) -> None:
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(k, raising=False)
    assert trace.is_enabled() is False


def test_span_is_a_noop_context_manager_when_disabled(monkeypatch) -> None:
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    # Must not raise and must yield a usable (possibly None) span id.
    with trace.span("node:propose", parent_id=None) as span_id:
        assert span_id is None or isinstance(span_id, str)


def test_flush_is_safe_when_disabled(monkeypatch) -> None:
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    with contextlib.suppress(Exception):
        trace.flush()  # must be a no-op, never raise
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_trace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capychem.loop.trace'`.

- [ ] **Step 3: Write `loop/trace.py`**

Defensive wrapper: gate on env keys; when enabled, lazily construct a Langfuse client and create spans; when anything in the Langfuse SDK path raises, degrade to a no-op rather than break the loop. `span()` is a context manager yielding a span id (or None) so the loop can thread `parent_id` through `LoopState` for nesting across async nodes.

```python
"""Langfuse span helpers for the loop.

No-ops when LANGFUSE_* keys are absent, so pytest/CI never need a running
Langfuse. When enabled, every node emits a span; nesting is maintained by
threading parent span ids through LoopState (contextvars are unreliable across
async ``await`` boundaries).

NOTE: targets the Langfuse v2 Python SDK (langfuse>=2,<3). If a different major
is installed, adapt the client/span calls inside the ``_enabled`` branches only —
the public surface (is_enabled / trace_run / span / flush) stays the same.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_REQUIRED_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


def is_enabled() -> bool:
    return all(os.environ.get(k) for k in _REQUIRED_KEYS)


_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        from langfuse import Langfuse  # imported lazily; only when enabled

        _client = Langfuse()
    return _client


def trace_run(run_id: int, task: str) -> str | None:
    """Open the top-level trace for a run; return its id (None when disabled)."""
    if not is_enabled():
        return None
    try:
        t = _get_client().trace(name="run", metadata={"run_id": run_id, "task": task})
        return str(t.id)
    except Exception:  # noqa: BLE001 - tracing must never break the loop
        return None


@contextmanager
def span(name: str, *, parent_id: str | None, **metadata: Any) -> Iterator[str | None]:
    """Context manager yielding the new span's id (or None when disabled/failed).

    ``parent_id`` is the enclosing trace or span id, threaded via LoopState.
    """
    if not is_enabled():
        yield None
        return
    sp = None
    try:
        sp = _get_client().span(name=name, trace_id=parent_id, metadata=metadata or None)
        yield str(sp.id)
    except Exception:  # noqa: BLE001
        yield None
    finally:
        if sp is not None:
            try:
                sp.end()
            except Exception:  # noqa: BLE001
                pass


def flush() -> None:
    """Flush buffered events (no-op when disabled)."""
    if not is_enabled():
        return
    try:
        _get_client().flush()
    except Exception:  # noqa: BLE001
        pass
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_trace.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Typecheck + commit**

Run: `uv run mypy -p capychem && uv run ruff check packages`
Expected: clean.

```bash
git add packages/core/capychem/loop/trace.py packages/core/tests/test_trace.py
git commit -m "feat(slice2): Langfuse span helpers with no-op fallback (no keys -> no-op)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 12: LangGraph loop wiring (the five nodes)

This is the orchestration. Pure logic is already covered by Task 10's tests; the node side-effects (DB writes, harness calls) are integration-tested by the CLI e2e test (Task 14). Keep nodes thin — they call `loop/logic.py`, `validate.py`, `oracle.py`, the session, and `trace.py`.

**Files:**
- Create: `packages/core/capychem/loop/graph.py`

- [ ] **Step 1: Write `loop/graph.py`**

```python
"""LangGraph runtime: propose -> validate -> score -> persist -> stop_check.

Nodes are async. State is LoopState (TypedDict); each node returns a partial dict
that LangGraph merges. Every node opens a Langfuse span as a child of the current
generation span (ids threaded through state). The harness is reached only via
oracle.py (subprocess); this module never imports harness code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from capychem.db.models import Candidate, Generation, OracleCall, Run
from capychem.loop import trace
from capychem.loop.logic import (
    build_summary,
    merge_and_truncate,
    stop_reason,
    trim_to_budget,
)
from capychem.loop.state import LoopState, Scored
from capychem.oracle import propose_offspring, score_smiles
from capychem.validate import validate_batch

_STARTING_POP = (
    Path(__file__).resolve().parents[4]
    / "harness"
    / "capychem_harness"
    / "data"
    / "starting_pop.smi"
)


def _load_starting_pop(limit: int) -> list[str]:
    lines = _STARTING_POP.read_text().splitlines()
    smis = [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    return smis[:limit]


def build_graph(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> CompiledStateGraph[LoopState]:
    """Compile the loop graph. ``sessionmaker`` is captured by the persist node."""

    async def propose(state: LoopState) -> dict[str, Any]:
        with trace.span("node:propose", parent_id=state.get("gen_span_id")):
            if state["gen_index"] == 0:
                raw = [(smi, None) for smi in _load_starting_pop(state["pop_size"])]
                proposer = "starting"
            else:
                pop = [(m.smiles, m.score) for m in state["population"]]
                children = propose_offspring(
                    pop,
                    state["offspring"],
                    mutation_rate=state["mutation_rate"],
                    seed=state["seed"] + state["gen_index"],  # per-gen derived seed (G6)
                )
                raw = [(c.smiles, c.parents) for c in children]
                proposer = "graph_ga"
            return {"proposed": raw, "_proposer": proposer}

    async def validate(state: LoopState) -> dict[str, Any]:
        with trace.span("node:validate", parent_id=state.get("gen_span_id")):
            return {"validated": validate_batch(state["proposed"])}

    async def score(state: LoopState) -> dict[str, Any]:
        with trace.span("node:score", parent_id=state.get("gen_span_id")):
            batch = trim_to_budget(
                state["validated"], budget=state["budget"], calls_used=state["calls_used"]
            )
            if not batch:
                return {"_scored": [], "calls_used": state["calls_used"]}
            results = score_smiles([c.smiles for c in batch], task=state["task"])
            scored = [
                (c, r.score)
                for c, r in zip(batch, results, strict=True)
                if r.valid and r.score is not None
            ]
            return {
                "_scored": scored,
                "calls_used": state["calls_used"] + len(scored),
            }

    async def persist(state: LoopState) -> dict[str, Any]:
        with trace.span("node:persist", parent_id=state.get("gen_span_id")):
            scored = state["_scored"]
            async with sessionmaker() as session:
                gen = Generation(
                    run_id=state["run_id"],
                    index=state["gen_index"],
                    proposer_used=state["_proposer"],
                )
                session.add(gen)
                await session.flush()  # gen.id

                pop = state["population"]
                new_scored: list[Scored] = []
                for vc, sc in scored:
                    parent_cid = None
                    if vc.parents is not None and pop:
                        parent_idx = vc.parents[0]
                        if 0 <= parent_idx < len(pop):
                            parent_cid = pop[parent_idx].candidate_id
                    cand = Candidate(
                        generation_id=gen.id,
                        smiles=vc.smiles,
                        parent_candidate_id=parent_cid,
                        proposer=state["_proposer"],
                        valid=True,
                        score=sc,
                    )
                    session.add(cand)
                    await session.flush()  # cand.id
                    session.add(
                        OracleCall(
                            run_id=state["run_id"],
                            candidate_id=cand.id,
                            task=state["task"],
                            score=sc,
                            wall_ms=0,
                            compute_cost_usd=0.0,
                        )
                    )
                    new_scored.append(
                        Scored(smiles=vc.smiles, score=sc, candidate_id=cand.id)
                    )
                await session.commit()

            survivors = merge_and_truncate(pop, new_scored, pop_size=state["pop_size"])
            top10 = sorted(survivors, key=lambda m: (-m.score, m.smiles))[:10]
            top10_mean = sum(m.score for m in top10) / len(top10) if top10 else 0.0
            curve = [*state.get("auc_curve", []), (state["calls_used"], top10_mean)]
            return {
                "population": survivors,
                "auc_curve": curve,
                "_made_progress": bool(new_scored),
            }

    async def stop_check(state: LoopState) -> dict[str, Any]:
        with trace.span("node:stop_check", parent_id=state.get("gen_span_id")):
            reason = stop_reason(
                calls_used=state["calls_used"],
                budget=state["budget"],
                gen_index=state["gen_index"] + 1,
                max_generations=state["max_generations"],
                made_progress=state["_made_progress"],
            )
            if reason is not None:
                summary = build_summary(
                    state["population"],
                    state.get("auc_curve", []),
                    generations=state["gen_index"] + 1,
                    oracle_calls=state["calls_used"],
                )
                return {"done": True, "stop_reason": reason, "summary": summary}
            return {"done": False, "gen_index": state["gen_index"] + 1}

    def route(state: LoopState) -> str:
        return "stop" if state.get("done") else "continue"

    builder: StateGraph = StateGraph(LoopState)
    builder.add_node("propose", propose)
    builder.add_node("validate", validate)
    builder.add_node("score", score)
    builder.add_node("persist", persist)
    builder.add_node("stop_check", stop_check)
    builder.set_entry_point("propose")
    builder.add_edge("propose", "validate")
    builder.add_edge("validate", "score")
    builder.add_edge("score", "persist")
    builder.add_edge("persist", "stop_check")
    builder.add_conditional_edges("stop_check", route, {"continue": "propose", "stop": END})
    return builder.compile()
```

Note: the transient carriers `_proposer`, `_scored`, `_made_progress` are already declared in `LoopState` (Task 10) — reading an undeclared TypedDict key is an unconditional mypy error (`TypedDict ... has no key`), so they are NOT optional. The `CompiledStateGraph[LoopState]` return annotation targets the installed LangGraph; if mypy reports a `type-arg` arity mismatch (the generic's parameter count differs across LangGraph versions), inspect it with `uv run python -c "from langgraph.graph.state import CompiledStateGraph; print(CompiledStateGraph)"` and adjust the type parameters (worst case `-> CompiledStateGraph[Any]`).

- [ ] **Step 2: Typecheck + lint**

Run: `uv run mypy -p capychem && uv run ruff check packages`
Expected: clean. (All node and `build_graph` return types are annotated; the only version-sensitive spot is the `CompiledStateGraph` generic arity — see note above.)

- [ ] **Step 3: Commit**

```bash
git add packages/core/capychem/loop/graph.py packages/core/capychem/loop/state.py
git commit -m "feat(slice2): LangGraph loop wiring (propose/validate/score/persist/stop_check)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 13: CLI `capychem-run`

**Files:**
- Create: `packages/core/capychem/cli.py`

(The `[project.scripts]` entry was added in Task 1.)

- [ ] **Step 1: Write `cli.py`**

```python
"""`capychem-run` — local end-to-end driver for the optimization loop.

Parses run config, creates a Run row, runs the LangGraph loop to budget/cap, and
prints a final summary. This is the slice's end-to-end proof.

Usage: capychem-run --task qed --budget 200 --seed 42 [--pop-size 100]
       [--offspring 32] [--mutation-rate 0.01] [--plateau-window 5]
       [--max-generations 100]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from capychem.db.models import Run
from capychem.db.session import init_schema, make_engine, make_sessionmaker
from capychem.loop import trace
from capychem.loop.graph import build_graph
from capychem.loop.state import LoopState


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="capychem-run")
    p.add_argument("--task", default="qed")
    p.add_argument("--budget", type=int, required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--pop-size", type=int, default=100)
    p.add_argument("--offspring", type=int, default=32)
    p.add_argument("--mutation-rate", type=float, default=0.01)
    p.add_argument("--plateau-window", type=int, default=5)
    p.add_argument("--max-generations", type=int, default=100)
    args = p.parse_args(argv)
    if args.budget <= 0:
        p.error("--budget must be a positive integer")  # FR-015
    if args.pop_size <= 1:
        p.error("--pop-size must be > 1 (crossover needs two parents)")
    return args


async def run(args: argparse.Namespace) -> dict[str, Any]:
    engine = make_engine()
    await init_schema(engine)
    sessionmaker = make_sessionmaker(engine)

    async with sessionmaker() as session:
        run_row = Run(
            task=args.task,
            budget=args.budget,
            mutation_strategy="graph_ga",
            plateau_window=args.plateau_window,
            pop_size=args.pop_size,
            offspring=args.offspring,
            mutation_rate=args.mutation_rate,
            seed=args.seed,
            status="running",
        )
        session.add(run_row)
        await session.commit()
        run_id = run_row.id

    run_span_id = trace.trace_run(run_id, args.task)
    graph = build_graph(sessionmaker)

    initial: LoopState = {
        "run_id": run_id,
        "task": args.task,
        "budget": args.budget,
        "seed": args.seed,
        "pop_size": args.pop_size,
        "offspring": args.offspring,
        "mutation_rate": args.mutation_rate,
        "plateau_window": args.plateau_window,
        "max_generations": args.max_generations,
        "calls_used": 0,
        "gen_index": 0,
        "population": [],
        "run_span_id": run_span_id,
        "gen_span_id": run_span_id,
        "auc_curve": [],
        "done": False,
    }
    # Each generation is 5 node-steps; allow headroom over the cap.
    recursion_limit = args.max_generations * 6 + 10
    final: LoopState = await graph.ainvoke(initial, config={"recursion_limit": recursion_limit})

    async with sessionmaker() as session:
        row = await session.get(Run, run_id)
        assert row is not None
        row.status = final.get("stop_reason") or "exhausted"
        row.summary_json = final.get("summary")
        await session.commit()

    trace.flush()
    await engine.dispose()
    summary = final.get("summary") or {}
    return {
        "run_id": run_id,
        "stop_reason": final.get("stop_reason"),
        "calls_used": final.get("calls_used"),
        # report completed-generation COUNT (summary's value = gen_index + 1), not the
        # last processed index, so the CLI print and summary_json agree.
        "generations": summary.get("generations"),
        "summary": final.get("summary"),
    }


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = asyncio.run(run(args))
    summary = result["summary"] or {}
    top = summary.get("top_k", [])[:10]
    print(f"\nRun {result['run_id']} — {result['stop_reason']}")
    print(f"  oracle calls used: {result['calls_used']}  generations: {result['generations']}")
    print("  top molecules:")
    for i, m in enumerate(top, 1):
        print(f"    {i:2d}. {m['score']:.4f}  {m['smiles']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the entry point resolves**

Run: `uv run capychem-run --help`
Expected: argparse usage text listing all flags. (Full run is exercised in Task 14.)

- [ ] **Step 3: Commit**

```bash
git add packages/core/capychem/cli.py
git commit -m "feat(slice2): capychem-run CLI — end-to-end local loop driver

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 14: End-to-end CLI test (real harness QED + Postgres)

**Files:**
- Test: `packages/core/tests/test_cli_e2e.py`

This test hits the real harness and a real Postgres. It is the slice's central proof. Postgres must be up.

- [ ] **Step 1: Write the test**

```python
"""End-to-end test: capychem-run on the real harness QED oracle + Postgres.

Small pop + a budget covering gen 0 + >=2 offspring generations, so monotonicity
is non-vacuous. Asserts rows persist with provenance, budget is never exceeded,
best-score is monotonic non-decreasing, and same seed -> identical top-K (G6).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from capychem.cli import parse_args, run
from capychem.db.models import Candidate, Generation, OracleCall
from capychem.db.session import make_engine, make_sessionmaker

# pop_size 20 (gen 0) + ~10 + ~10 ≈ 40 scored calls fits in 60 with headroom.
_ARGV = [
    "--task", "qed", "--budget", "60", "--seed", "42",
    "--pop-size", "20", "--offspring", "10", "--max-generations", "50",
]


@pytest.mark.asyncio
async def test_cli_run_persists_and_is_monotonic() -> None:
    result = await run(parse_args(_ARGV))
    run_id = result["run_id"]
    assert result["calls_used"] <= 60  # FR-002: never exceeds budget
    assert result["generations"] >= 2  # monotonicity is non-vacuous

    engine = make_engine()
    sessionmaker = make_sessionmaker(engine)
    async with sessionmaker() as session:
        gens = (await session.execute(
            select(Generation).where(Generation.run_id == run_id).order_by(Generation.index)
        )).scalars().all()
        assert len(gens) >= 3  # gen 0 + >=2 offspring gens

        n_calls = (await session.execute(
            select(func.count()).select_from(OracleCall).where(OracleCall.run_id == run_id)
        )).scalar_one()
        assert n_calls == result["calls_used"]

        # gen-0 candidates have no parent; gen->=1 candidates do.
        gen0_cands = (await session.execute(
            select(Candidate).where(Candidate.generation_id == gens[0].id)
        )).scalars().all()
        assert gen0_cands and all(c.parent_candidate_id is None for c in gen0_cands)

        later_cands = (await session.execute(
            select(Candidate).where(Candidate.generation_id == gens[-1].id)
        )).scalars().all()
        assert later_cands and any(c.parent_candidate_id is not None for c in later_cands)
    await engine.dispose()

    # best-score-so-far monotonic non-decreasing across the AUC curve
    curve = result["summary"]["auc_curve"]
    means = [pt["top10_mean"] for pt in curve]
    assert means == sorted(means), f"top-10 mean must be non-decreasing: {means}"


@pytest.mark.asyncio
async def test_cli_run_is_deterministic_for_same_seed() -> None:
    a = await run(parse_args(_ARGV))
    b = await run(parse_args(_ARGV))
    top_a = [(m["smiles"], round(m["score"], 6)) for m in a["summary"]["top_k"]]
    top_b = [(m["smiles"], round(m["score"], 6)) for m in b["summary"]["top_k"]]
    assert top_a == top_b
```

- [ ] **Step 2: Ensure pytest-asyncio is available**

The async tests need `pytest-asyncio`. Add it to the dev group and configure auto mode:

In root `pyproject.toml` `[dependency-groups]` dev list, add `"pytest-asyncio>=0.24"`. In `[tool.pytest.ini_options]` (create the section if absent) add `asyncio_mode = "auto"`.

Run: `uv sync`

- [ ] **Step 3: Run the test** (Postgres up; harness venv present)

Run: `docker compose -f infra/compose.yml up -d && uv run pytest packages/core/tests/test_cli_e2e.py -v`
Expected: PASS (2 tests). The run takes a few seconds (real QED scoring). If `test_..._deterministic` fails, a non-seeded RNG leaked in — check the per-gen seed (`seed + gen_index`) is threaded and the survivor tiebreak is canonical-SMILES.

- [ ] **Step 4: Commit**

```bash
git add packages/core/tests/test_cli_e2e.py pyproject.toml uv.lock
git commit -m "test(slice2): end-to-end CLI run — persistence, provenance, budget, monotonicity, G6

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 15: Extend `scripts/smoke.sh` with a loop check

**Files:**
- Modify: `scripts/smoke.sh`

- [ ] **Step 1: Add a loop smoke check** before the "Infra containers reachable" block (so Postgres is already expected up by the existing pg check; move the loop check AFTER the pg `up -d`). Insert after line 49 (`docker compose -f infra/compose.yml up -d ...`) and before the langfuse block:

```bash
# 6. End-to-end loop: a tiny CLI run lands rows in Postgres (slice 2 gate).
check "loop e2e (capychem-run QED, tiny budget)" \
  uv run capychem-run --task qed --budget 40 --pop-size 20 --offspring 10 --seed 42
```

- [ ] **Step 2: Run the full smoke suite**

Run: `scripts/smoke.sh`
Expected: all checks pass (the prior 8 + the new loop check). The final line reads `== N passed, 0 failed ==`.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke.sh
git commit -m "test(slice2): add loop e2e check to smoke.sh

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 16: Final gate + slice-shipping docs

**Files:**
- Modify: `docs/00-walking-skeleton/milestone.md` (slice status flip)
- Modify: `docs/00-walking-skeleton/handoff.md` (overwrite)
- Modify: `docs/00-walking-skeleton/01-local-loop.md` (freeze — created during this slice's session)

- [ ] **Step 1: Full green gate**

Run:
```bash
uv run pytest packages/core/tests -q
uv run mypy -p capychem
uv run ruff check packages apps/api
uv run ruff format --check packages
scripts/smoke.sh
```
Expected: all pass; smoke ends `== N passed, 0 failed ==`. Do not proceed until every command is green. (If `ruff format --check` flags files, run `uv run ruff format packages` and re-commit.)

- [ ] **Step 2: Verify the slice exit criteria** (design doc §Exit criteria) against reality:
  - `capychem-run --task qed --budget <small> --seed 42` completes end-to-end ✓ (Task 14/15).
  - Run/Generation/Candidate/OracleCall rows persist with correct provenance ✓ (Task 14 asserts gen-0 NULL, gen≥1 populated).
  - Same seed → identical top-K ✓ (Task 14 determinism test).
  - No `import` from `harness/` in `packages/` or `apps/`: run `grep -rn "import.*harness\|from harness\|capychem_harness" packages apps` — expect NO hits referencing the harness package (the only crossing is the subprocess path strings in `oracle.py`, which are not imports).
  - Langfuse nested trace: optional/manual — set `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` and run once; confirm a run→generation→node trace appears. CI does not require it.

- [ ] **Step 3: Author + freeze the slice doc** `docs/00-walking-skeleton/01-local-loop.md` (≤2 pages, per `~/.claude/CLAUDE.md`): Goal / Plan (files touched) / Tasks (this checklist, all ticked) / Notes (deferrals: plateau, authoritative AUC, population override, cross-gen memoization). Mark status shipped.

- [ ] **Step 4: Flip milestone + handoff** (per CLAUDE.md "when a slice ships" — all in one commit):
  - `milestone.md` Slices list: `01-local-loop` → shipped; advance `02-web-surface` note as next.
  - `handoff.md` overwrite (20–40 lines): Completed this session (slice 2 + commit refs); Slice status (`01-local-loop` → shipped); Current state (branch `main`, loop runs locally on QED); **Next session start here** = open slice 3 (`02-web-surface`): FastAPI REST + WS + Next.js launch/live view; Active concerns.
  - **Correct the stale handoff line**: slice 2 did NOT install full `mol_opt` — it vendored only the Jensen `crossover.py`/`mutate.py` operators (no PyTorch). Full `mol_opt` + `BaseOptimizer` baseline reproduction remains deferred to milestone 01. Record this so the next session doesn't re-litigate it.

- [ ] **Step 5: Ship commit**

```bash
git add docs/00-walking-skeleton/
git commit -m "docs(slice2): ship 01-local-loop — flip milestone/handoff, freeze slice doc

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review notes (verify before executing)

- **FR coverage:** FR-001 partial (CLI config, not web — web is slice 3) ✓; FR-002 budget enforcement (trim + stop) ✓; FR-004 validate-before-score ✓; FR-006 score + provenance ✓ (Task 14 asserts it); FR-008 persist full history ✓; FR-015 refuse non-positive budget ✓ (CLI). FR-003 (plateau), FR-005 (LLM→fallback), FR-007 (analyzer), FR-009..FR-014 (WS/UI/cost/trace-link) are explicitly deferred per the design's Deferred section — not in scope this slice.
- **Type consistency:** `Scored(smiles, score, candidate_id)`, `ValidCandidate(smiles, parents)`, `Offspring(smiles, parents)` are used consistently across `validate.py`, `loop/state.py`, `loop/graph.py`, `oracle.py`, and tests. `propose_offspring` takes `list[tuple[str, float]]` everywhere. `stop_reason`/`trim_to_budget`/`merge_and_truncate`/`build_summary` signatures match between `logic.py` and `test_loop_logic.py`.
- **Harness import path:** `propose.py` runs by path, so it self-inserts the harness root onto `sys.path` (Task 4) to import `capychem_harness.graph_ga`; the Task 2 verification heredoc uses `PYTHONPATH=harness` for the same reason. This is load-bearing — without it the package is unimportable and the proposer dies on the first offspring generation.
- **Known soft spots to watch during execution (flagged, not blocking):**
  1. Vendored Jensen operators — Task 2 verifies signatures + no-torch + a live import; if `mol_opt`'s copies differ in signature (extra args, nested vs module-level `crossover`/`mutate`), adjust `propose.py`'s call sites to match and re-run Task 4 Step 2.
  2. Langfuse SDK major — `trace.py` targets v2; if a v3 client is installed, adapt only the enabled branches (Task 11 note). The enabled path isn't CI-exercised; a mismatch surfaces only in the manual Langfuse check (Task 16).
  3. LangGraph `recursion_limit` — set in `cli.py`; if a long run stops early with a recursion error, raise the multiplier. The `CompiledStateGraph` generic arity may also vary by version (Task 12 note).
  4. mypy + TypedDict transient keys — the `_`-prefixed carriers are declared in `LoopState` up front (Task 10), so this is resolved, not deferred.
