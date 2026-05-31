#!/usr/bin/env bash
# CapyChem walking-skeleton smoke test — the slice-1 (00-foundation) exit gate.
#
# Proves every seam end to end:
#   - the isolated harness exists and a REAL QED score crosses the subprocess bridge
#   - modern code passes strict types + lint + the bridge test
#   - the Next.js web app compiles
#   - the Postgres + Langfuse containers are reachable
#
# Usage: scripts/smoke.sh   (from anywhere; it cd's to the repo root)
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PASS=0
FAIL=0

check() { # name, command...
  local name="$1"
  shift
  printf '▶ %s\n' "$name"
  if "$@" >/tmp/capychem-smoke.log 2>&1; then
    printf '  ✓ %s\n' "$name"
    PASS=$((PASS + 1))
  else
    printf '  ✗ %s (see /tmp/capychem-smoke.log)\n' "$name"
    tail -n 5 /tmp/capychem-smoke.log | sed 's/^/    /'
    FAIL=$((FAIL + 1))
  fi
}

# 1. Isolated harness venv (Python 3.10 + PyTDC), reached only via subprocess.
check "harness venv present" test -x "$ROOT/harness/.venv/bin/python"

# 2. Real QED score across the harness↔modern bridge + invalid-SMILES handling.
check "oracle bridge (QED via PyTDC)" uv run pytest packages/core/tests -q

# 3. Modern code quality gates.
check "ruff" uv run ruff check packages apps/api
check "mypy (strict)" uv run mypy -p capychem

# 4. Web app compiles.
check "web typecheck" pnpm --filter web typecheck
check "web lint" pnpm --filter web lint

# 5. Infra containers reachable (idempotent up; nothing reads them yet in slice 1).
docker compose -f infra/compose.yml up -d >/dev/null 2>&1 || true
check "postgres pg_isready" docker exec capychem-postgres pg_isready -U "${POSTGRES_USER:-capychem}"
docker compose -f infra/langfuse-compose.yml up -d >/dev/null 2>&1 || true
check "langfuse health" bash -c \
  'curl -fsS --retry 30 --retry-delay 2 --retry-connrefused http://localhost:3001/api/public/health'

printf '\n== %d passed, %d failed ==\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
