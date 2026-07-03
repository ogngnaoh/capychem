# Slice 06-04 — axe-core CI accessibility gate

**Status:** shipped (frozen)

## Goal
Lock in the 06-03 remediation with an automated axe-core gate so a11y regressions can't silently return.

## What shipped
- `apps/web/e2e/a11y.spec.ts` — Playwright + `@axe-core/playwright` across all 5 routes (`/`, `/launch`, `/runs`, `/runs/{id}`, `/compare`) in **light + dark** at 1280px, tagged wcag2a/2aa/21a/21aa, failing on **serious/critical** violations. Reuses the existing `mockApi`/`forceDark` shot fixtures (FastAPI origin route-mocked → no backend/Postgres/WS needed; a completed snapshot renders the full cockpit without a WebSocket).
- `@axe-core/playwright` devDependency (package.json + pnpm-lock.yaml).
- `.github/workflows/ci.yml` web job: `playwright install --with-deps chromium` + `playwright test e2e/a11y.spec.ts` after the vitest step.

## Acceptance — met
- `pnpm exec playwright test e2e/a11y.spec.ts` → **10 passed** (independently re-run).
- The gate fails loudly if any route regresses below AA (verified: it caught the pre-existing muted-foreground/coral/dl/scrollable failures before 06-03 fixed them).

## Notes
- CI-only chromium install via `--with-deps` (ubuntu runner has sudo); local runs reuse the already-installed browser.
- The shot specs (screenshot capture) are NOT run in CI — only `a11y.spec.ts` is targeted.
