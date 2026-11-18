# Contributing to CapyChem

CapyChem Studio is a local molecular-design workspace for running and reviewing
versioned CDK2 experiments. Start with recorded evidence for UI work. Install the
science runtime when changing candidate generation, preparation, docking, or
scientific review. Neither path requires an LLM key or cloud GPU.

## Choose a development loop

Use Node 22+, pnpm 11.5.0, Python 3.12, and [uv](https://docs.astral.sh/uv/).
Run commands below from the repository root.

### Recorded workspace: frontend work

```bash
pnpm install --frozen-lockfile
pnpm studio
```

Open <http://127.0.0.1:5181/?mode=demo>. The bundled results are saved scientific
evidence, not fresh inference. This mode does not need Python, PostgreSQL, models,
or API credentials. New experiment submissions require the live stack.

### Live Studio: API, worker, and scientific computation

The validated automatic science setup is macOS on Apple silicon. Install
PostgreSQL 16+ locally, or supply an existing development database with
`scripts/dev.py --database-url ...`. Docker is optional for this path.

```bash
uv sync --frozen --python 3.12
pnpm install --frozen-lockfile
uv python install 3.11
.venv/bin/python scripts/setup_science.py \
  --python "$(uv python find 3.11)" --with-generator
.venv/bin/python scripts/dev.py
```

The setup script creates isolated Python 3.11 science and LibInvent environments,
downloads pinned model/source dependencies, verifies reference hashes, and writes
`.science/setup-manifest.json`. These downloads are explicit and can be sizable.
Omit `--with-generator` to evaluate supplied candidates without installing the
generator. RDKit, Meeko, AutoDock Vina, PoseBusters, and ProLIF perform the chemistry
and pose analysis; the pinned REINVENT4 LibInvent model proposes candidates.

The launcher reads that manifest, applies database migrations, and starts a
FastAPI process, a separate experiment worker, and the Studio. Defaults are API
port 8001, Studio port 5181, and a local PostgreSQL cluster on port 55433. Use
`--api-port`, `--studio-port`, and `--postgres-port` to avoid another running stack.
The database lives in `.local/postgres`; scientific artifacts live in
`.local/artifacts`. Do not use a database containing someone else's experiments
for tests or release validation.

On other platforms, automatic Vina installation is not implemented. Supply the
official Vina 1.2.7 binary through `--vina-binary`. Dependency installation alone
does not establish support: run the scientific checks below and report the OS,
architecture, package versions, and results before describing that platform as
validated. Existing science/generator environments can be registered through
the setup script's `--science-python` and `--generator-python` options.

### Legacy benchmark app

`apps/web` and the PMO/Graph-GA engine remain covered by CI. They are separate from
the new Studio workflow. Their tests need the isolated legacy harness:

```bash
uv sync --frozen --project harness
docker compose -f infra/compose.yml up -d postgres
uv run uvicorn capychem.api.main:app --reload --port 8000
# In a second terminal:
pnpm --filter web dev
```

The legacy web app opens on port 3000. `infra/compose.yml`'s API/runner services
serve this legacy engine; they do not install the new Studio science runtime.
Do not import the Python 3.10/PyTDC harness into the modern application. Use its
existing JSON subprocess bridge.

## Automated checks

CI has three independent jobs: backend, legacy web, and Studio. It does not
install the Studio science runtime or download the LibInvent checkpoint. A green
CI run is a software-contract check, not a fresh docking benchmark.

### Backend, including real PostgreSQL queue behavior

Provision **dedicated test databases**. For a fresh Docker PostgreSQL service:

```bash
docker compose -f infra/compose.yml up -d postgres
docker compose -f infra/compose.yml exec -T postgres createdb -U capychem capychem_api_test
docker compose -f infra/compose.yml exec -T postgres createdb -U capychem capychem_studio_test
```

Create these once; adjust the credentials/port for your local PostgreSQL. The
legacy API tests use `CAPYCHEM_DATABASE_URL`, while Studio tests use a separate
`CAPYCHEM_TEST_DATABASE_URL` whose database name must end in `_test`. Each Studio
test creates and removes its own schema. Without the latter variable, the
convenience SQLite path skips PostgreSQL concurrency and timezone checks.

```bash
export CAPYCHEM_DATABASE_URL=postgresql+asyncpg://capychem:capychem@127.0.0.1:5432/capychem_api_test
export CAPYCHEM_TEST_DATABASE_URL=postgresql+asyncpg://capychem:capychem@127.0.0.1:5432/capychem_studio_test
uv sync --frozen --project harness
uv run ruff check .
uv run mypy -p capychem -p capychem.api
uv run pytest -q -ra
```

Read the skip summary: absent harness/PostgreSQL dependencies can skip legacy
integration tests. Real-science tests deliberately require the opt-in variables
below. CI builds the harness and provisions both database URLs. CI checks Ruff
lint; repository-wide `ruff format --check` is not yet an enforced baseline.

### Studio production build and recorded browser flows

```bash
pnpm build:studio
pnpm --dir apps/studio exec playwright install chromium
CAPYCHEM_E2E_LIVE=0 pnpm --dir apps/studio exec playwright test \
  --config playwright.ci.config.ts
```

`build:studio` includes TypeScript checking. The CI Playwright configuration
starts and stops a fresh production preview on port 5189; set
`CAPYCHEM_STUDIO_CI_PORT` if occupied. It never reuses your live Studio server.
The recorded tests cover navigation, input recovery, evidence comparison,
preferred-pose identity, exports, and study browsing. Live-only tests are
explicitly skipped. Linux CI installs Chromium's system dependencies with
`playwright install --with-deps chromium` and retains failure traces/screenshots.

### Legacy web

```bash
pnpm --filter web lint
pnpm --filter web typecheck
pnpm --filter web test
pnpm --filter web exec playwright install chromium
pnpm --filter web exec playwright test e2e/a11y.spec.ts
```

The accessibility test starts its own dev server and mocks the API. It checks
serious/critical axe violations on legacy routes in both themes.

## Scientific release gate (explicit local computation)

Run this after scientific pipeline changes and before a release that claims live
inference support. First install/register the science runtime, then load its
generated environment and run the real CPU checks:

```bash
source .science/science.env
PYTHONPATH="$PWD/packages/core" \
CAPYCHEM_TEST_SCIENCE_PYTHON="$CAPYCHEM_SCIENCE_PYTHON" \
  uv run pytest -q -ra packages/core/tests/test_experiment_science.py
```

Then start the API and worker in a disposable development database/artifact
directory using `scripts/dev.py`. Replay the versioned control baseline against
that API (port 8001 below) into a new output directory:

```bash
uv run python scripts/validate_science_api.py
uv run python scripts/validate_science_api.py \
  --api http://127.0.0.1:8001 \
  --baseline data/validation/cdk2/growth-v2-baseline-v2.json \
  --science-python "$CAPYCHEM_SCIENCE_PYTHON" \
  --output-dir .local/release-validation/control-replay \
  --run

uv run python scripts/validate_science_api.py \
  --api http://127.0.0.1:8001 \
  --baseline data/validation/cdk2/input-capability-v1.json \
  --science-python "$CAPYCHEM_SCIENCE_PYTHON" \
  --output-dir .local/release-validation/input-matrix \
  --run
```

The first command lists cases without submitting work. The second submits new
known-positive, mixed-input, strict-filter, and generated batches, downloads their
evidence, and checks contracts and scientific comparisons. It requires the
generator setup. Keep the reports, hashes, versions, failure reasons, and run
durations as release evidence. Exit codes are 0 for pass, 1 for execution/preflight
failure, 2 for a contract failure, and 3 for scientific review required.

The input matrix adds three fixed seeds across neutral analogs and explicit or
unspecified stereochemistry, then checks malformed/disconnected/dummy/charged
graphs, tautomer duplicates, scaffold/attachment boundaries, all-filtered batches,
and candidate budgets. Its original pre-execution declaration is retained next to
the reviewed fixture. These checks preserve input and evidence integrity; they
do not establish affinity or general docking accuracy.

An engine/dependency change may invalidate the baseline fingerprint. Investigate
the difference before running with `--allow-engine-change`; this flag enables a
comparison but does not bless changed results. Review the saved evidence and
version the baseline deliberately. Do not silently regenerate expected values to
make a failing check green.

For live browser coverage, use the ordinary `playwright.config.ts` against a
running Studio with `CAPYCHEM_STUDIO_URL` and `CAPYCHEM_E2E_LIVE=1`. These tests
submit real work. Review each spec's fixture requirements first: scientific
review tests accept `CAPYCHEM_E2E_*_EXPERIMENT` IDs, and study creation additionally
requires `CAPYCHEM_E2E_STUDY_LAUNCH=1`. Never point them at an operator's workspace.

## Contribution invariants

- Keep molecular identity, input provenance, preparation, protocol, model, seed,
  and artifact hashes traceable. Preserve invalid/duplicate raw input outcomes;
  only validated molecules proceed to evaluation.
- Keep predicted contacts, geometry validity, and the design objective distinct.
  A docking score or objective hit is not experimental binding or efficacy.
  A completed no-hit batch is a legitimate result.
- Persist exact pose identity in selections and exports. Do not silently switch
  a saved decision to another pose or overwrite another tab's decision.
- Keep recorded and live results visibly distinguishable. Do not imply a bundled
  demonstration launched inference.
- Preserve immutable experiment intent, idempotent submission, attempt ownership,
  cancellation, and recovery behavior when changing workers or APIs.
- Legacy benchmark runs remain separate from exploratory objectives, custom
  seeds, constraints, and the Studio. Do not broaden benchmark claims from a new
  UI or docking result. Legacy LLM/oracle costs must still reconcile in `RunCost`.

Never commit credentials, local databases, downloaded model weights, or private
input structures. `.science`, `.local`, and `.env.local` are ignored. Describe
what changed, the commands you actually ran, and any skipped or unvalidated paths
in your pull request.
