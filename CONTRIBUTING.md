# Contributing to CapyChem

CapyChem is a single-developer portfolio build, but it is structured to be
**forked and run locally**. This guide is what you need to get a dev loop going
and the invariants you must not break.

## Dev setup

Prerequisites: Python 3.12 + [`uv`](https://docs.astral.sh/uv/), Node 22 + `pnpm`, Docker.

```bash
# Modern Python (core + api) and the isolated legacy harness (PyTDC 0.3.6 / Python 3.10)
uv sync
uv sync --project harness

# Node
pnpm install

# Env: copy the template, fill in what you need (the defaults run key-free)
cp .env.example .env.local

# Local infra
docker compose -f infra/compose.yml up -d            # Postgres
docker compose -f infra/langfuse-compose.yml up -d   # Langfuse (optional)

# Schema (also applied automatically on API startup, apps/api/capychem/api/main.py)
uv run alembic upgrade head

# Run the stack
uv run uvicorn capychem.api.main:app --reload        # API → :8000
pnpm --filter web dev                                 # web → :3000
```

The default proposer/analyzer/oracle backends are `stub`/`local` — deterministic,
network-free, no API keys. Set `CAPYCHEM_PROPOSER_BACKEND=direct` + `DEEPSEEK_API_KEY`
to use the real model. You do **not** need a Modal account to run locally.

## Checks (what CI runs)

Run these before opening a PR — CI runs the same commands on the key-free path:

```bash
# Python
uv run ruff check .
uv run ruff format --check .
uv run mypy -p capychem -p capychem.api
uv run pytest                          # API tests need a local Postgres (infra/compose.yml)

# Web
pnpm --filter web lint
pnpm --filter web typecheck
pnpm --filter web test
pnpm --filter web exec playwright test  # visual-regression shots; axe-core a11y gate lands in 06-04
```

## Invariants (do not break these)

- **In-silico only (N6).** Every score is an in-silico oracle score. Never claim
  real-world drug-discovery efficacy in code, copy, or docs. The defensible claim is
  *"a genuinely usable in-silico lead/hit-optimization tool a computational chemist
  could drive against their own scoring function."*
- **Figure canon.** The benchmark result is "beats/matches vanilla Graph-GA on all
  **21 comparable** PMO tasks (seed 42, 10k budget); **2 of 23 excluded for cause**."
  Never write "21/23", and never claim SOTA.
- **Benchmark vs. exploratory mode.** (Landing in milestone 07.) Any custom seed,
  custom oracle, composed objective, or constraint makes a run `exploratory` — it must
  never be tagged `benchmark` or feed the committed G1 numbers. This is enforced in
  code + tests, not just docs.
- **Never import from `harness/`.** The legacy PMO/PyTDC stack is pinned and isolated;
  modern code talks to it only via the JSON subprocess bridge in
  `packages/core/capychem/oracle.py`.
- **Validate every SMILES with RDKit before persistence.** Never trust LLM or operator
  output as valid.
- **Cost is first-class.** Every LLM and oracle call updates `RunCost`; `total_usd`
  must sum both.

## Project layout

See the "Repository map" in the root [`README.md`](README.md). Work is organized as
milestones (`docs/NN-<name>/`) containing vertical slices; the active milestone is
marked in `docs/milestones.md`.

## Secrets

Never commit real secrets. `.env.local` is gitignored; deployed secrets live in the
host environment / Modal's secret store. Generate strong local secrets with
`openssl rand -hex 32`.
