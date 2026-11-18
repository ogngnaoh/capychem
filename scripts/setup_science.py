#!/usr/bin/env python3
"""Install or register CapyChem's isolated CPU science tools.

Default: python scripts/setup_science.py --python python3.11
Add --with-generator for the optional LibInvent prior (about 90 MB) and CPU Torch.
Pass --science-python/--generator-python to register existing environments without
installing into them. Runtime dependencies remain separate from the web/API venv.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/core"))
from capychem.experiments.science_config import (  # noqa: E402
    LIBINVENT_SHA256,
    REINVENT_COMMIT,
    load_preset,
    supported_presets,
)

MODEL_URL = "https://zenodo.org/api/records/15641297/files/libinvent.prior/content"
VINA_URL = (
    "https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.7/vina_1.2.7_mac_aarch64"
)
VINA_SHA256 = "823c2bbacf26d72183861322345f0a89736aca66c8e81054c66f93af5ad623f1"


def command(args, **kwargs):
    print("Running:", " ".join(shlex.quote(str(arg)) for arg in args), flush=True)
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, path: Path, expected_sha: str):
    if path.exists():
        if digest(path) != expected_sha:
            raise ValueError(f"Existing download does not match the registered checksum: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".download")
    if shutil.which("curl"):
        command(
            [
                "curl",
                "--fail",
                "--location",
                "--retry",
                "2",
                "--max-time",
                "600",
                url,
                "--output",
                temporary,
            ]
        )
    else:
        import urllib.request

        with urllib.request.urlopen(url, timeout=600) as response, temporary.open("wb") as stream:
            shutil.copyfileobj(response, stream)
    if digest(temporary) != expected_sha:
        temporary.unlink()
        raise ValueError(f"Downloaded file failed its registered SHA256: {url}")
    temporary.replace(path)


def environment(base_python: str, directory: Path, requirements: list[str]) -> str:
    python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        command([base_python, "-m", "venv", directory])
    command([python, "-m", "pip", "install", *requirements])
    return str(python.absolute())


def absolute_executable(value: str) -> str:
    path = Path(value).expanduser()
    found = str(path.absolute()) if path.is_file() else shutil.which(value)
    if not found:
        raise ValueError(f"Executable not found: {value}")
    # Do not resolve a virtualenv python symlink into the system interpreter.
    return found


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", default="python3.11", help="Interpreter used to create isolated environments"
    )
    parser.add_argument("--directory", type=Path, default=ROOT / ".science")
    parser.add_argument(
        "--science-python", help="Register an existing science interpreter; do not install into it"
    )
    parser.add_argument("--vina-binary", help="Register an existing AutoDock Vina 1.2.7 binary")
    parser.add_argument("--with-generator", action="store_true")
    parser.add_argument("--generator-python", help="Register an existing LibInvent interpreter")
    parser.add_argument(
        "--reinvent-source", type=Path, help="Existing REINVENT4 checkout at the pinned commit"
    )
    parser.add_argument(
        "--checkpoint", type=Path, help="Existing official LibInvent prior; checksum checked"
    )
    args = parser.parse_args()
    destination = args.directory.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / ".gitignore").write_text("*\n!.gitignore\n")
    preset = load_preset()
    presets = supported_presets(verify=True)
    if args.science_python:
        science_python = absolute_executable(args.science_python)
    else:
        science_python = environment(
            args.python,
            destination / "cpu",
            ["-r", str(ROOT / "data/reference/cdk2/science-requirements.txt")],
        )
    # Verify imports and record exact installed versions without modifying them.
    imports = (
        "import rdkit,numpy,meeko,posebusters,prolif; "
        "import importlib.metadata as m,json; "
        "print(json.dumps({k:m.version(k) "
        "for k in ['rdkit','numpy','meeko','posebusters','prolif']}))"
    )
    versions = (
        subprocess.check_output([science_python, "-c", imports], text=True).strip().splitlines()[-1]
    )
    if args.vina_binary:
        vina = Path(absolute_executable(args.vina_binary))
    elif platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}:
        vina = destination / "vina"
        download(VINA_URL, vina, VINA_SHA256)
        vina.chmod(0o755)
    else:
        raise ValueError(
            "Automatic binary setup is validated on Apple silicon. "
            "Supply --vina-binary with your platform's official Vina 1.2.7 release."
        )
    version = subprocess.check_output([str(vina), "--version"], text=True).strip()
    if "1.2.7" not in version:
        raise ValueError("The baseline protocol requires Vina 1.2.7")
    config = {
        "CAPYCHEM_SCIENCE_PYTHON": science_python,
        "CAPYCHEM_VINA_BINARY": str(vina.absolute()),
        "CAPYCHEM_CDK2_DATA_DIR": str(ROOT / "data/reference/cdk2"),
    }
    generator_versions = None
    if args.with_generator:
        generator_python = (
            absolute_executable(args.generator_python)
            if args.generator_python
            else environment(
                args.python,
                destination / "generator",
                ["-r", str(ROOT / "data/reference/cdk2/generator-requirements.txt")],
            )
        )
        generator_imports = (
            "import torch,rdkit,numpy,molvs,xxhash,pydantic,tqdm; "
            "import importlib.metadata as m,json; "
            "print(json.dumps({k:m.version(k) "
            "for k in ['torch','rdkit','numpy','molvs','xxhash','pydantic','tqdm']}))"
        )
        generator_versions = json.loads(
            subprocess.check_output([generator_python, "-c", generator_imports], text=True)
            .strip()
            .splitlines()[-1]
        )
        source = (
            args.reinvent_source.expanduser().resolve()
            if args.reinvent_source
            else destination / "REINVENT4"
        )
        if not source.exists():
            command(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    "https://github.com/MolecularAI/REINVENT4.git",
                    source,
                ]
            )
            command(["git", "checkout", "--detach", REINVENT_COMMIT], cwd=source)
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source, text=True
        ).strip()
        if commit != REINVENT_COMMIT:
            raise ValueError(
                f"Existing REINVENT checkout must be at {REINVENT_COMMIT}; it was not changed"
            )
        changes = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=source, text=True
        ).strip()
        if changes:
            raise ValueError("REINVENT checkout contains tracked modifications; it was not changed")
        checkpoint = (
            args.checkpoint.expanduser().resolve()
            if args.checkpoint
            else destination / "libinvent.prior"
        )
        if args.checkpoint and not checkpoint.is_file():
            raise ValueError("The specified checkpoint file does not exist")
        download(MODEL_URL, checkpoint, LIBINVENT_SHA256)
        config.update(
            CAPYCHEM_GENERATOR_PYTHON=generator_python,
            CAPYCHEM_REINVENT_SOURCE=str(source),
            CAPYCHEM_LIBINVENT_CHECKPOINT=str(checkpoint),
        )
    env_file = destination / "science.env"
    atomic_write(
        env_file,
        "# Load in the server/worker environment. No secrets.\n"
        + "".join(f"export {key}={shlex.quote(value)}\n" for key, value in config.items()),
    )
    atomic_write(
        destination / "setup-manifest.json",
        json.dumps(
            {
                "preset": preset["id"],
                "presets": [item["id"] for item in presets],
                "versions": json.loads(versions),
                "generator_versions": generator_versions,
                "vina_version": version,
                "vina_sha256": digest(vina),
                "configuration": config,
            },
            indent=2,
        )
        + "\n",
    )
    print(f"Science configured. The launcher reads {destination / 'setup-manifest.json'}.")
    if destination != ROOT / ".science":
        print(
            "Start with scripts/dev.py --science-config "
            + shlex.quote(str(destination / "setup-manifest.json"))
        )
    print(f"For manual API/worker startup, load {env_file}.")
    print(
        "Reference hashes and dependency imports verified. "
        "Run the real science smoke test before treating a new machine as validated."
    )


if __name__ == "__main__":
    main()
