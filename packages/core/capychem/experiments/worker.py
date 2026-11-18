"""One local scientific worker, with real subprocess execution and durable recovery.

Run with ``python -m capychem.experiments.worker``. The separate scientific Python
environment is selected explicitly by CAPYCHEM_SCIENCE_PYTHON.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import sys
import uuid
from pathlib import Path
from time import monotonic
from typing import Any

from capychem.db.session import make_engine, make_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .artifacts import attempt_directory
from .queue import Claim, claim_next, finish, heartbeat, record_progress, renew
from .runtime import configuration_fingerprint, probe_runtime
from .science_config import engine_fingerprint
from .service import ingest_report, publish_diagnostics, reference_manifest

logger = logging.getLogger(__name__)


async def stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        await process.wait()


def read_report(directory: Path) -> dict[str, Any] | None:
    path = directory / "report.json"
    if not path.is_file():
        return None
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Science process returned an unsupported report schema.")
    return value


async def execute(sm: async_sessionmaker[AsyncSession], claim: Claim) -> None:
    started = monotonic()
    wall_seconds = claim.spec.get("resolved_protocol", {}).get("wall_time_limit_seconds", 7200)
    directory: Path | None = None
    python = os.environ.get("CAPYCHEM_SCIENCE_PYTHON", sys.executable)
    env = os.environ.copy()
    core_source = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [core_source, env.get("PYTHONPATH", "")]))
    # Bound tool-internal threads separately from process concurrency.
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env.setdefault(key, "1")
    process: asyncio.subprocess.Process | None = None
    lease_lost = asyncio.Event()
    cancelled = asyncio.Event()
    timed_out = asyncio.Event()
    monitor_task: asyncio.Task[None] | None = None
    try:
        # Storage/setup failures belong to this attempt, not the worker process.
        directory = attempt_directory(claim.attempt_id)
        input_path = directory / "input.json"
        input_path.write_text(json.dumps(claim.spec, indent=2) + "\n")
        expected = claim.spec.get("resolved_protocol", {}).get("target_manifest_sha256")
        if (
            expected
            and reference_manifest(claim.spec["target_preparation_id"])["manifest_sha256"]
            != expected
        ):
            raise ValueError(
                "Target preparation changed after submission; create a new experiment."
            )
        expected_engine = claim.spec.get("resolved_protocol", {}).get("engine_fingerprint")
        if not expected_engine or engine_fingerprint() != expected_engine:
            raise ValueError(
                "Scientific implementation changed or was not recorded at submission; "
                "fork a new experiment to run the current engine."
            )
        with (directory / "stderr.log").open("wb") as stderr:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-u",
                "-m",
                "capychem.experiments.supervisor",
                "--",
                python,
                "-u",
                "-m",
                "capychem.experiments.science",
                "--input",
                str(input_path),
                "--output-dir",
                str(directory),
                stdout=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                stderr=stderr,
                env=env,
                start_new_session=os.name == "posix",
                limit=1024 * 1024,
            )

            async def monitor() -> None:
                while True:
                    try:
                        async with asyncio.timeout(10):
                            await heartbeat(sm, claim.worker_id)
                            owned, should_cancel = await renew(sm, claim)
                    except Exception:
                        # If ownership cannot be checked, stop this process. A
                        # later worker can reclaim the lease; this attempt must
                        # not keep computing after its heartbeat task has died.
                        logger.exception("Unable to renew experiment lease")
                        lease_lost.set()
                        await stop_process(process)
                        return
                    if not owned:
                        lease_lost.set()
                        await stop_process(process)
                        return
                    if should_cancel:
                        cancelled.set()
                        await stop_process(process)
                        return
                    if monotonic() - started >= wall_seconds:
                        timed_out.set()
                        await stop_process(process)
                        return
                    await asyncio.sleep(2)

            monitor_task = asyncio.create_task(monitor())
            assert process.stdout is not None
            with (directory / "progress.jsonl").open("w") as stream:
                while line := await process.stdout.readline():
                    stream.write(line.decode("utf-8", errors="replace"))
                    stream.flush()
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    if not await record_progress(sm, claim, event):
                        lease_lost.set()
                        await stop_process(process)
                        break
                    if event.get("type") in (
                        "candidate.complete",
                        "candidate.completed",
                        "report.updated",
                    ):
                        report = read_report(directory)
                        if report is not None:
                            await ingest_report(sm, claim, directory, report)
            returncode = await process.wait()
        if lease_lost.is_set():
            return
        await publish_diagnostics(sm, claim, directory)
        report = read_report(directory)
        if report:
            await ingest_report(sm, claim, directory, report, final=True)
        if cancelled.is_set():
            await finish(sm, claim, "cancelled")
        elif timed_out.is_set():
            await record_progress(
                sm,
                claim,
                {
                    "type": "attempt.deadline_exceeded",
                    "stage": "interrupted",
                    "wall_time_limit_seconds": wall_seconds,
                },
            )
            await finish(
                sm,
                claim,
                "failed",
                f"Scientific calculation exceeded its {wall_seconds}s wall-clock limit.",
            )
        elif returncode != 0 or (report and report.get("status") == "failed"):
            reason = (report or {}).get("error")
            if not isinstance(reason, str):
                reason = (
                    f"Scientific process exited with code {returncode}. "
                    "Inspect its recorded stderr log."
                )
            await finish(sm, claim, "failed", reason[:4000])
        elif report is None:
            await finish(sm, claim, "failed", "Scientific process exited without a result report.")
        elif report.get("status") != "complete":
            await finish(
                sm, claim, "failed", "Scientific process exited with an incomplete report."
            )
        else:
            errors = any(
                r.get("partial")
                or r.get("pose_errors")
                or r.get("status") in {"evaluation_error", "no_pose"}
                or any(a.get("status") == "failed" for a in r.get("embedding_attempts", []))
                for r in report.get("records", [])
            )
            await finish(sm, claim, "completed_with_errors" if errors else "completed")
    except asyncio.CancelledError:
        if process is not None:
            await stop_process(process)
        # A worker shutdown is not a user cancellation. Leave the lease to expire;
        # the next worker creates a recorded new attempt under the same spec.
        raise
    except Exception as exc:
        if process is not None:
            await stop_process(process)
        logger.exception("Experiment %s failed", claim.experiment_id)
        if directory is not None:
            try:
                await publish_diagnostics(sm, claim, directory)
            except Exception:
                logger.exception("Could not publish failed-attempt diagnostics")
        await finish(sm, claim, "failed", f"{type(exc).__name__}: {exc}"[:4000])
    finally:
        if monitor_task:
            monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task


async def run_forever(poll_seconds: float = 1.0, probe_retry_seconds: float = 30.0) -> None:
    engine = make_engine()
    sm = make_sessionmaker(engine)
    worker_id = f"science-{uuid.uuid4().hex[:12]}"
    logger.info("Local experiment worker %s checking runtime", worker_id)
    health: dict[str, Any] = {
        "state": "checking",
        "configuration_fingerprint": configuration_fingerprint(),
    }
    probe: asyncio.Task[dict[str, Any]] | None = None
    next_probe_at = 0.0
    try:
        while True:
            try:
                fingerprint = configuration_fingerprint()
                changed = health.get("configuration_fingerprint") != fingerprint
                retry_due = monotonic() >= next_probe_at and (
                    health.get("state") == "unavailable"
                    or (
                        health.get("generator", {}).get("configured")
                        and not health["generator"].get("ok")
                    )
                )
                if probe is None and (health["state"] == "checking" or changed or retry_due):
                    if changed or health["state"] != "ready":
                        health = {"state": "checking", "configuration_fingerprint": fingerprint}
                    # Retain verified science readiness while only an optional
                    # generator probe retries; supplied jobs can still proceed.
                    probe = asyncio.create_task(probe_runtime())
                if probe is not None and probe.done():
                    try:
                        health = probe.result()
                    except Exception as exc:
                        logger.exception("Runtime probe failed unexpectedly; retrying later")
                        health = {
                            "state": "unavailable",
                            "configuration_fingerprint": fingerprint,
                            "science": {"ok": False, "message": str(exc) or type(exc).__name__},
                        }
                    probe = None
                    next_probe_at = monotonic() + probe_retry_seconds
                await heartbeat(sm, worker_id, health)
                if health.get("state") != "ready":
                    await asyncio.sleep(poll_seconds)
                    continue
                claim = await claim_next(sm, worker_id)
                if claim:
                    if claim.spec["candidate_source"]["kind"] == "libinvent" and not health.get(
                        "generator", {}
                    ).get("ok"):
                        await finish(
                            sm,
                            claim,
                            "failed",
                            "LibInvent runtime is unavailable; check engine setup.",
                        )
                    else:
                        await execute(sm, claim)
                else:
                    await asyncio.sleep(poll_seconds)
            except (SQLAlchemyError, OSError):
                logger.exception("Worker connection or storage unavailable; retrying")
                await asyncio.sleep(poll_seconds)
    finally:
        if probe:
            probe.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await probe
        with contextlib.suppress(SQLAlchemyError, OSError):
            await heartbeat(sm, worker_id, {**health, "state": "stopped"})
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logger.info("Experiment worker stopped; unfinished attempts remain reclaimable.")


if __name__ == "__main__":
    main()
