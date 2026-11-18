"""Bounded worker-side dependency probes; the API never imports chemistry."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifacts import artifact_root
from .science_config import readiness, reference_data_dir


def configuration_fingerprint() -> str:
    paths = {
        name: os.environ.get(name, "")
        for name in (
            "CAPYCHEM_SCIENCE_PYTHON",
            "CAPYCHEM_VINA_BINARY",
            "CAPYCHEM_GENERATOR_PYTHON",
            "CAPYCHEM_REINVENT_SOURCE",
            "CAPYCHEM_LIBINVENT_CHECKPOINT",
            "CAPYCHEM_CDK2_DATA_DIR",
        )
    }
    paths["default_python"] = sys.executable
    paths["artifact_root"] = str(artifact_root())
    signatures: dict[str, list[int] | None] = {}
    candidates = [Path(p).expanduser() for key, p in paths.items() if p and key != "artifact_root"]
    candidates.extend([reference_data_dir() / "manifest.json", *Path(__file__).parent.glob("*.py")])
    candidates.extend(reference_data_dir().joinpath("preparations").glob("*/manifest.json"))
    candidates.extend(Path(__file__).parent.joinpath("chemistry").glob("*.py"))
    for name in ("CAPYCHEM_SCIENCE_PYTHON", "CAPYCHEM_GENERATOR_PYTHON"):
        if paths[name]:
            environment = Path(paths[name]).expanduser().parent.parent
            candidates.append(environment / "pyvenv.cfg")
            candidates.extend(environment.glob("lib/python*/site-packages"))
    for path in candidates:
        try:
            stat = path.stat()
            signatures[str(path)] = [stat.st_size, stat.st_mtime_ns]
        except OSError:
            signatures[str(path)] = None
    return hashlib.sha256(
        json.dumps({"paths": paths, "files": signatures}, sort_keys=True).encode()
    ).hexdigest()


async def probe_command(command: list[str], *, timeout: float = 45) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(Path(__file__).resolve().parents[2]), env.get("PYTHONPATH", "")])
    )
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        start_new_session=os.name == "posix",
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except (TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
        raise
    if process.returncode:
        error = stderr.decode(errors="replace").strip().splitlines()
        raise ValueError(error[-1][:500] if error else f"Runtime probe exited {process.returncode}")
    result = json.loads(stdout.decode().strip().splitlines()[-1])
    if not isinstance(result, dict):
        raise ValueError("Runtime probe returned an invalid response")
    return result


SCIENCE_PROBE = """
import importlib, importlib.metadata, json, os, subprocess
from pathlib import Path
from capychem.experiments.science_config import (
    executable, load_preset, supported_presets, VINA_VERSION,
)
packages = ['rdkit', 'numpy', 'meeko', 'posebusters', 'prolif']
for name in packages:
    importlib.import_module(name)
for preset in supported_presets():
    load_preset(preset['id'], verify=True)
vina = executable('CAPYCHEM_VINA_BINARY', 'vina')
if not vina:
    raise ValueError('Configure the Vina executable')
version = subprocess.check_output([vina, '--version'], text=True, timeout=10).strip()
if VINA_VERSION not in version:
    raise ValueError('Vina version differs from the registered protocol')
print(json.dumps({'versions': {name: importlib.metadata.version(name) for name in packages},
                  'vina': version}))
"""

GENERATOR_PROBE = """
import importlib.metadata, json, os, subprocess, sys
from pathlib import Path
from capychem.experiments.science_config import LIBINVENT_SHA256, REINVENT_COMMIT, sha256
source = Path(os.environ['CAPYCHEM_REINVENT_SOURCE'])
checkpoint = Path(os.environ['CAPYCHEM_LIBINVENT_CHECKPOINT'])
if sha256(checkpoint) != LIBINVENT_SHA256:
    raise ValueError('LibInvent checkpoint integrity check failed')
commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=source,
                                 text=True, timeout=10).strip()
dirty = subprocess.check_output(['git','status','--porcelain','--untracked-files=no'], cwd=source,
                                text=True, timeout=10).strip()
if commit != REINVENT_COMMIT or dirty:
    raise ValueError('REINVENT source must match the clean registered revision')
sys.path.insert(0, str(source.resolve()))
import torch
from reinvent.models.libinvent.models.model import DecoratorModel
saved = torch.load(checkpoint, map_location='cpu', weights_only=False)
if saved.get('model_type') != 'Libinvent':
    raise ValueError('Checkpoint is not LibInvent')
DecoratorModel.create_from_dict(saved, 'inference', torch.device('cpu'))
print(json.dumps({'versions': {p: importlib.metadata.version(p) for p in ['torch','rdkit','numpy']},
                  'checkpoint_sha256': LIBINVENT_SHA256, 'source_commit': commit}))
"""


async def probe_runtime() -> dict[str, Any]:
    health: dict[str, Any] = {
        "configuration_fingerprint": configuration_fingerprint(),
        "checked_at": datetime.now(UTC).isoformat(),
        "state": "unavailable",
        "science": {"ok": False},
        "generator": {"ok": False},
    }
    config = readiness()
    try:
        if not config["configured"]:
            raise ValueError("; ".join(config["problems"]))
        root = artifact_root()
        root.mkdir(parents=True, exist_ok=True)
        # Check the actual store without leaving test artifacts behind.
        import tempfile

        with tempfile.TemporaryFile(dir=root) as handle:
            handle.write(b"artifact-store-probe")
            handle.flush()
            os.fsync(handle.fileno())
        result = await probe_command([config["science_python"], "-c", SCIENCE_PROBE])
        health["science"] = {"ok": True, **result}
        health["state"] = "ready"
    except Exception as exc:
        health["science"] = {"ok": False, "message": str(exc) or type(exc).__name__}
    if config["libinvent_configured"]:
        try:
            result = await probe_command(
                [os.environ.get("CAPYCHEM_GENERATOR_PYTHON", sys.executable), "-c", GENERATOR_PROBE]
            )
            health["generator"] = {"ok": True, "configured": True, **result}
        except Exception as exc:
            health["generator"] = {
                "ok": False,
                "configured": True,
                "message": str(exc) or type(exc).__name__,
            }
    else:
        health["generator"] = {
            "ok": False,
            "configured": False,
            "message": "Optional LibInvent environment is not configured.",
        }
    return health
