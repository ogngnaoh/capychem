# Slice 06-06 — reliability: recoverable pause + oracle retry + Modal n>1 fix

**Status:** shipped (frozen)

## Goal
Make an oracle-worker fault recoverable (PRD edge-case-2) instead of a hard `errored` that loses work, absorb transient harness blips, and fix the latent Modal `propose` n>1 crash.

## What shipped
- **Recoverable pause (Part A, `runner.py`):** `_drive` catches `HarnessError` distinctly *before* the broad `except Exception` → status `"paused"` + a persisted partial `summary_json` (reuses the `build_summary` fallback proven for cost_capped/stopped), so the interrupted run's partial results stay browseable. `asyncio.CancelledError` still propagates (shutdown unaffected). `paused`/`errored`/`cost_capped` are mutually exclusive.
- **Transient-blip retry (Part B, `graph.py`):** a generic `_with_harness_retry(call)` wraps **every** harness-subprocess call — scoring (`score_batch_async`) AND Graph-GA offspring/fallback (`strategy.ga_fill`/`fallback_fill`, which run `propose_offspring`). Bounded (3 attempts, async backoff 0.5s/1.0s), re-raises the last `HarnessError` on exhaustion so a sustained outage pauses (Part A) rather than the loop spinning. The helper handles sync (GA) and async (score) thunks via `inspect.isawaitable`.
- **Modal `propose` fix (Part D, `apps/worker/app.py`):** replaced the `n:n` call (DeepSeek caps n=1 → 400) with a `ThreadPoolExecutor` fan-out of n single-`n=1` requests, per-index seed `seed+i`, each with its own usage (no even-split); a per-request transient failure (402/429/5xx or a requests exception) degrades to an empty row via the pure, unit-tested `_choice_to_row` helper, mirroring `proposer._direct_propose`. Order-preserving (`[f.result() for f in futures]`), context-managed executor. Modal-only path — verified by inspection + the helper's unit tests (not locally runnable).
- **Web:** `"paused"` added to LiveRun's `TERMINAL` set; StatusChip/RunsBrowse/Overview treat status as an opaque string (no enum to break).

## Acceptance — met (independently verified)
- `test_pause_recover.py`: a sustained oracle fault → status `"paused"` (not `errored`) with a non-null partial summary; DB row + snapshot reflect it.
- `test_loop_score_retry.py` (4 tests): a one-off blip is absorbed on the score path (integration) AND on a **sync GA call** (unit); an async call retries; a sustained fault re-raises after 3 attempts.
- `test_worker_propose.py` (7 tests): `_choice_to_row` good→row-with-own-usage; 402/429/500/503/network→empty row; hard 400→raises.
- Full `pytest` green; `mypy` 47 clean; `ruff` clean.

## Review + fix
An adversarial Critic pass found a **major** gap: the initial retry covered only the score path, but `propose_offspring` (the **default** graph_ga strategy's hot path + the FR-005 fallback filler) raised the same `HarnessError` unretried — a single blip there would pause the run prematurely. Fixed by generalizing `_score_with_retry` → `_with_harness_retry` and routing all three harness call sites through it, with direct unit tests for the sync-GA and sustained-fault cases.

## Deferred
Durable in-process resume (reconstruct loop state from persisted rows + a resume action + startup sweep → paused) is **06-07** — a `paused` run is browseable with saved partial state, but resuming it is the next slice.
