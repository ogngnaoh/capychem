# Slice 06-01 — repo hygiene, fork-and-run docs, env origins, cost-gate reconciliation

**Status:** shipped (frozen)

## Goal
Make the repo cleanly forkable and honestly documented, with env-driven CORS origins and the SPEC cost-gate text reconciled to the shipped flat cap — no behavior change to the engine.

## What shipped
- `LICENSE` — MIT, with a third-party note documenting that the legacy GPL harness is subprocess-isolated (never imported/linked), so MIT is clean.
- `CONTRIBUTING.md` — dev setup, the exact CI-check commands, and the project invariants (N6, figure canon "never 21/23", mode split [07], no harness import, RDKit-validate, cost first-class).
- `apps/web/README.md` — rewritten from create-next-app boilerplate to a real app README (routes, scripts, layout, a11y target framed as forthcoming in 06-03/06-04, not present-tense).
- `.env.example` — added the two Langfuse SDK keys, `ALLOWED_ORIGINS`, and the `CAPYCHEM_ORACLE_BACKEND`/`ORACLE_USD_PER_SEC`/`COST_CAP_USD` vars; corrected the analyzer/intent backend semantics (analyzer `modal` unimplemented; intent is an inert `llm`-only seam); Modal marked OPTIONAL.
- `README.md` — light fork-and-run touch (no-auth/no-hosting note + CONTRIBUTING pointer); every G1 honesty caveat preserved; objective-ownership NOT claimed (it is milestone 07). CI badge deferred to 06-02.
- `apps/api/capychem/api/config.py` — `parse_origins()` makes `ALLOWED_ORIGINS` comma-separated env-driven; `main.py` (CORS) and `ws_runs.py` (WS handshake) both read the one parsed list.
- `SPEC.md §8.3` — reconciled to the shipped flat, env-tunable, reactive `$50` cap (`cost_capped`); the never-built "1.5× projected budget" language removed.

## Acceptance — met
- `test_cors_origins.py` (4 tests) green: env parse + both sites read the same object.
- Cost gate already covered by `apps/api/tests/test_cost_gate.py` (3 tests) — no duplicate added; SPEC now matches code.
- `ruff check` + `ruff format --check` + `mypy -p capychem -p capychem.api` (42 files) clean.
- Adversarial Critic pass: 2 MAJOR honesty defects found (a11y/axe overclaim in web README + CONTRIBUTING; false analyzer/intent backend semantics in `.env.example`) — both fixed and re-verified against source.
- No "21/23" in any user-facing doc; no real-world-efficacy claim; no un-built feature asserted as present.

## Notes
- LICENSE copyright line uses "Hoang Ngo" (from the repo owner's git email); trivially editable if the legal name differs.
- The a11y target and CI-check references in docs are forward-facing (land in 06-02/03/04 on this same branch before merge).
