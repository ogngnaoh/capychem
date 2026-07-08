# syntax=docker/dockerfile:1
#
# CapyChem multi-target image (milestone 08 slice 06 — ops maturity).
#
# One Dockerfile, two runnable targets (`api` and `runner`), so both images
# share an IDENTICAL harness build and an identical uv workspace build —
# there is exactly one place either can drift. Build context is the REPO
# ROOT (the image needs packages/core, apps/api, apps/runner, and harness/):
#
#   docker build -f infra/Dockerfile --target api    -t capychem-api    .
#   docker build -f infra/Dockerfile --target runner -t capychem-runner .
#
# infra/compose.yml builds both via `build.target`.
#
# --- Honesty about oracle scoring in-container -----------------------------
# The oracle-scoring subprocess bridge (packages/core/capychem/oracle) shells
# out to an isolated Python-3.10 interpreter running `capychem_harness/score.py`
# — the legacy PyTDC 0.3.6 env (CLAUDE.md gotcha: never imported, only ever
# invoked as a subprocess). This image bakes that SAME harness/ source the
# repo ships into its own `harness` build stage below (copied into the final
# image at /opt/harness-py310, pointed at via CAPYCHEM_HARNESS_PYTHON), so a
# container built from this Dockerfile scores PMO/TDC oracles exactly as
# local dev does — this is in-silico benchmark scoring (RDKit + PyTDC oracle
# functions), never live docking or any wet-lab process (N6, non-goal N2).
# If a constrained build environment cannot complete the `harness` stage
# (e.g. no network egress for its pinned wheels), the `api`/`runner` images
# still build and serve REST/WS/health/readiness; any run that reaches the
# score node then raises HarnessError and the run pauses in a recoverable
# state (the same oracle-fault path a local harness outage takes, PRD edge
# case 2) rather than fabricating a score.
# -----------------------------------------------------------------------------

FROM python:3.10-slim AS harness
RUN pip install --no-cache-dir uv
WORKDIR /harness
# harness/ is `[tool.uv] package = false` (never a workspace member) — this
# stage only needs to materialize its pinned dependency set (PyTDC 0.3.6,
# RDKit, etc.), not build a local package. Deliberately installed with plain
# `pip` into this stage's SYSTEM site-packages, not `uv sync`'s venv: a uv venv's
# `bin/python` is a symlink back to `/usr/local/bin/python3` of WHATEVER image
# invokes it, which breaks the instant that venv directory is copied into a
# different base image (the final image below is python:3.12-slim, whose
# `/usr/local/bin/python3` is Python 3.12, not this stage's 3.10). Installing
# straight into `/usr/local`'s own site-packages instead means this ENTIRE
# stage's `/usr/local` (real 3.10 interpreter + stdlib + shared libs +
# packages) is self-contained and safe to copy verbatim into another image.
COPY harness/pyproject.toml harness/uv.lock ./
RUN uv export --frozen --no-dev --no-hashes -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS workspace
RUN pip install --no-cache-dir uv
WORKDIR /repo
COPY pyproject.toml uv.lock alembic.ini ./
COPY packages/core ./packages/core
COPY apps/api ./apps/api
COPY apps/runner ./apps/runner
# Syncs the whole workspace (capychem-core + capychem-api + capychem-runner)
# into one venv shared by both final targets below — simplest correct option;
# the modest extra size of installing apps/runner's deps into the api image
# (and vice versa) is not worth a second, subtly-divergent lockfile resolve.
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime-base
# RDKit's Draw module (routes_molecule.py's 2D-structure SVG rendering) needs
# libXrender at import time; python:3.12-slim has no X11 libs by default.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxrender1 libxext6 libexpat1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /repo
COPY --from=workspace /repo /repo
# The harness stage's ENTIRE Python 3.10 install (interpreter + stdlib +
# shared libs + PyTDC/RDKit), namespaced under /opt so it can never collide
# with this image's own /usr/local (Python 3.12, the app's own venv). Both
# base images share the same Debian release, so their OS-level shared libs
# (glibc, libssl, zlib, ...) are compatible.
COPY --from=harness /usr/local /opt/harness-py310
# The harness's own source (score.py / propose.py / graph_ga mutation ops) —
# oracle.py resolves these by path relative to the repo root at runtime.
COPY harness/capychem_harness /repo/harness/capychem_harness
ENV PATH="/repo/.venv/bin:${PATH}"
# Points oracle._harness_python() at the copied 3.10 interpreter directly (an
# existing override hook, packages/core/capychem/oracle) instead of its
# default `harness/.venv/bin/python` lookup -- there is no venv in this image.
ENV CAPYCHEM_HARNESS_PYTHON=/opt/harness-py310/bin/python3.10
# Unbuffered stdout so `docker compose logs -f api|runner` shows log lines as
# they happen, not only on buffer flush.
ENV PYTHONUNBUFFERED=1

FROM runtime-base AS api
EXPOSE 8000
CMD ["uvicorn", "capychem.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime-base AS runner
CMD ["python", "-m", "capychem_runner"]
