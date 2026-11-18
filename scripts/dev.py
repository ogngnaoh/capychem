#!/usr/bin/env python3
"""Start the local studio, API and scientific worker with one command.

Run with the workspace Python after uv sync and science setup. By default a
dedicated native Postgres cluster is kept under .local/postgres (loopback only).
Pass --database-url to use an existing Postgres instead. No Docker is required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], **kwargs):
    return subprocess.run(command, check=True, cwd=ROOT, **kwargs)


def postgres_bin() -> Path:
    configured = os.environ.get("CAPYCHEM_POSTGRES_BIN")
    candidates = [Path(configured)] if configured else []
    found = shutil.which("pg_ctl")
    if found:
        candidates.append(Path(found).parent)
    candidates.extend(
        Path(p)
        for p in (
            "/opt/homebrew/opt/postgresql@16/bin",
            "/usr/local/opt/postgresql@16/bin",
            "/usr/lib/postgresql/16/bin",
            "/usr/lib/postgresql/17/bin",
            "/opt/homebrew/opt/postgresql@18/bin",
        )
    )
    for path in candidates:
        if all(
            os.access(path / name, os.X_OK) for name in ("pg_ctl", "initdb", "psql", "createdb")
        ):
            version = subprocess.check_output([str(path / "pg_ctl"), "--version"], text=True)
            match = re.search(r"\(PostgreSQL\)\s+(\d+)", version)
            if not match or int(match[1]) < 16:
                continue
            return path
    raise RuntimeError("Install PostgreSQL 16+ or pass --database-url for an existing database.")


def port_available(port: int):
    with socket.socket() as connection:
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            connection.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"Port {port} is occupied. Choose another port.") from exc


def local_postgres(port: int) -> str:
    binary = postgres_bin()
    data = ROOT / ".local/postgres"
    data.parent.mkdir(exist_ok=True)
    socket_dir = ROOT / ".local/pg-socket"
    socket_dir.mkdir(exist_ok=True)
    if not (data / "PG_VERSION").is_file():
        run(
            [
                str(binary / "initdb"),
                "-D",
                str(data),
                "-U",
                "capychem",
                "--auth=trust",
                "--encoding=UTF8",
                "--no-locale",
            ],
            stdout=subprocess.DEVNULL,
        )
    status = subprocess.run(
        [str(binary / "pg_ctl"), "-D", str(data), "status"], capture_output=True
    )
    if status.returncode != 0:
        port_available(port)
        # Unix socket path has a small platform limit. TCP is sufficient here.
        run(
            [
                str(binary / "pg_ctl"),
                "-D",
                str(data),
                "-l",
                str(data.parent / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {port} -k '' -c timezone=UTC",
                "start",
            ],
            stdout=subprocess.DEVNULL,
        )
    else:
        # pg_ctl status identifies this data directory, but the requested port
        # might point at a different server. Never query/create its databases.
        try:
            actual_port = int((data / "postmaster.pid").read_text().splitlines()[3])
        except (OSError, ValueError, IndexError) as exc:
            raise RuntimeError(
                "Cannot verify the running local database port; inspect .local/postgres."
            ) from exc
        if actual_port != port:
            raise RuntimeError(
                f"The CapyChem database is already running on port {actual_port}. "
                f"Use --postgres-port {actual_port}, "
                "or stop that cluster before choosing another port."
            )
    connection = ["-h", "127.0.0.1", "-p", str(port), "-U", "capychem"]
    exists = subprocess.check_output(
        [
            str(binary / "psql"),
            *connection,
            "-d",
            "postgres",
            "-tAc",
            "SELECT 1 FROM pg_database WHERE datname = 'capychem_studio'",
        ],
        text=True,
    ).strip()
    if exists != "1":
        run([str(binary / "createdb"), *connection, "capychem_studio"])
    return f"postgresql+asyncpg://capychem@127.0.0.1:{port}/capychem_studio"


def stop(process: subprocess.Popen):
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGINT)
    else:
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def load_science_config(path: Path, env: dict[str, str]) -> None:
    if not path.is_file():
        if path != ROOT / ".science/setup-manifest.json":
            raise RuntimeError(f"Science configuration does not exist: {path}")
        print(
            "Science setup is not registered. Run scripts/setup_science.py; "
            "the workspace can open, but calculations need a ready local engine.",
            flush=True,
        )
        return
    try:
        config = json.loads(path.read_text())["configuration"]
        if not isinstance(config, dict) or any(
            not isinstance(key, str)
            or not key.startswith("CAPYCHEM_")
            or not isinstance(value, str)
            for key, value in config.items()
        ):
            raise ValueError("Expected string CAPYCHEM_ configuration entries")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Invalid science configuration at {path}. Re-run scripts/setup_science.py."
        ) from exc
    for key, value in config.items():
        env.setdefault(key, value)


def valid_port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535")
    return port


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("CAPYCHEM_DATABASE_URL"))
    parser.add_argument("--postgres-port", type=valid_port, default=55433)
    parser.add_argument("--api-port", type=valid_port, default=8001)
    parser.add_argument("--studio-port", type=valid_port, default=5181)
    parser.add_argument(
        "--science-config", type=Path, default=ROOT / ".science/setup-manifest.json"
    )
    parser.add_argument("--no-ui", action="store_true", help="Only start API and worker")
    args = parser.parse_args()
    env = os.environ.copy()
    load_science_config(args.science_config, env)
    env["CAPYCHEM_INLINE_WORKER"] = "0"
    env.setdefault("CAPYCHEM_ARTIFACT_DIR", str(ROOT / ".local/artifacts"))
    env["CAPYCHEM_API_URL"] = f"http://127.0.0.1:{args.api_port}"
    port_available(args.api_port)
    if not args.no_ui:
        if args.api_port == args.studio_port:
            raise RuntimeError("API and studio need distinct ports.")
        port_available(args.studio_port)
        if not shutil.which("pnpm"):
            raise RuntimeError("Install pnpm and run pnpm install before starting the studio.")
    env["CAPYCHEM_DATABASE_URL"] = args.database_url or local_postgres(args.postgres_port)
    processes: list[subprocess.Popen] = []

    def start(command: list[str]):
        process = subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=os.name == "posix")
        processes.append(process)
        return process

    def interrupt(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, interrupt)
    try:
        api = start(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "capychem.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.api_port),
            ]
        )
        # The API applies migrations before workers can claim tasks.
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if api.poll() is not None:
                raise RuntimeError("API startup failed; see its output above.")
            try:
                with urllib.request.urlopen(f"{env['CAPYCHEM_API_URL']}/healthz", timeout=1):
                    break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.25)
        else:
            raise RuntimeError("API did not become healthy within 45 seconds.")
        start([sys.executable, "-m", "capychem.experiments.worker"])
        if not args.no_ui:
            start(
                [
                    "pnpm",
                    "--dir",
                    "apps/studio",
                    "exec",
                    "vite",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.studio_port),
                    "--strictPort",
                ]
            )
        print(f"\nCapyChem API: {env['CAPYCHEM_API_URL']}", flush=True)
        if not args.no_ui:
            print(f"CapyChem studio: http://127.0.0.1:{args.studio_port}", flush=True)
        print(
            "Ctrl+C stops the app and worker. Database files and experiments persist.\n", flush=True
        )
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        raise RuntimeError("A service stopped unexpectedly; see its output above.")
    finally:
        for process in reversed(processes):
            stop(process)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"CapyChem: {error}", file=sys.stderr)
        sys.exit(1)
