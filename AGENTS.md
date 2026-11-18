# Working on CapyChem

## What belongs in Git

Commit source, migrations, locked dependencies, tests, the public README, this guide, and required licenses and notices. Include a data file only when a shipped workflow or a reproducibility check reads it. Keep its source, redistribution terms and expected digest alongside the relevant manifest or test.

Put plans, PRDs, design references, review notes, screenshots, launch-film projects, renders, benchmark run reports and scratch experiments under the ignored `.local/`. Build distributable archives into `dist/` or attach them to a release. Keep drafts, local databases, environment files, private molecule inputs, worker logs, caches and downloaded model weights out of commits. The curated recordings under `apps/studio/public/data/` power the offline product and its tests. Review their provenance, public contents and hashes before updating them.

Keep user setup and the first working example in `README.md`. Put implementation details next to code, configuration or tests. When removing material, search for runtime file reads, package metadata, Docker COPY paths, tests, and links. Check what is actually tracked with `git ls-files` and validate from a clean checkout.

## Runtime boundaries

- `apps/studio` is the React/Three.js workspace. `apps/api` serves the experiment contract. `packages/core/capychem/experiments` owns queueing, computation and artifact identity. The API and CLI use Alembic for PostgreSQL schema changes.
- Preserve immutable input specs, seeds, attempt ownership, idempotent submissions, cancellation, and recovery. Keep each selected pose tied to its exact artifact and SHA-256 through review, export and restart.
- Keep supplied, generated, observed and calculated structures distinguishable. Preserve rejected and duplicate inputs. A completed run may find zero target contacts. Contact geometry and docking scores support inspection. They do not establish binding affinity.
- Keep the Python 3.12 application, Python 3.11 science runtime, optional LibInvent environment, and Python 3.10 legacy PMO harness isolated. The legacy harness is called through its JSON subprocess interface.

## Verification

Install with the frozen uv and pnpm lockfiles. CI commands and supported Linux browser runners are in [the workflow](.github/workflows/ci.yml).

- **Backend.** Install the legacy harness with `uv sync --frozen --project harness`. Point `CAPYCHEM_DATABASE_URL` and `CAPYCHEM_TEST_DATABASE_URL` at separate disposable PostgreSQL databases. The latter name must end in `_test`. Run `uv run ruff check .`, `uv run mypy -p capychem -p capychem.api` and `uv run pytest -q -ra`. Check the skip summary.
- **Studio.** Run `pnpm build:studio`, install Chromium with `pnpm --dir apps/studio exec playwright install chromium`, then run `pnpm --dir apps/studio exec playwright test --config playwright.ci.config.ts`. CI also runs the legacy web tests and accessibility checks.
- **Science.** After changing scientific behavior, start a disposable live stack using the README. Load `.science/science.env`, then run the four-case control comparison below. The generated case needs the optional LibInvent setup. Use a new output directory per run. Inspect any changed engine fingerprint or scientific result before accepting a new version of a baseline. Preserve the original baseline and held-out coordinates.
- **Distribution.** Test both README entry points from a clean checkout when changing setup, packaging or demo data. For the offline path, select a candidate, inspect its contact, open a study cell, and verify that the downloaded pose matches the recorded hash. Report separately which recorded and live checks ran.

```sh
source .science/science.env
python3 scripts/validate_science_api.py --run \
  --api http://127.0.0.1:8001 \
  --baseline data/validation/cdk2/growth-v2-baseline-v2.json \
  --science-python "$CAPYCHEM_SCIENCE_PYTHON" \
  --output-dir .local/release-validation/control-replay
```

Running the validator without `--run` lists cases. Exit code 2 signals a contract or artifact failure. Exit code 3 calls for scientific review, including a changed engine fingerprint. The held-out crystal pose is read only after inference, for independent comparison.
