"""Content-addressed local artifacts with verified, atomic publication."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any


def artifact_root() -> Path:
    return Path(os.environ.get("CAPYCHEM_ARTIFACT_DIR", ".capychem/artifacts")).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attempt_directory(attempt_id: str) -> Path:
    path = artifact_root() / "attempts" / attempt_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def publish_file(base: Path, relative: str, experiment_id: str, attempt_id: str) -> dict[str, Any]:
    source = (base / relative).resolve()
    if not source.is_relative_to(base.resolve()) or not source.is_file():
        raise ValueError("Artifact must be a regular file inside its attempt directory.")
    logical_path = source.relative_to(base.resolve()).as_posix()
    if len(logical_path) > 512:
        raise ValueError("Artifact relative path is too long.")
    checksum = sha256_file(source)
    storage_key = f"blobs/{checksum[:2]}/{checksum}"
    destination = artifact_root() / storage_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        descriptor, temporary = tempfile.mkstemp(prefix=".publish-", dir=destination.parent)
        try:
            with os.fdopen(descriptor, "wb") as out, source.open("rb") as src:
                shutil.copyfileobj(src, out)
                out.flush()
                os.fsync(out.fileno())
            if sha256_file(Path(temporary)) != checksum:
                raise ValueError("Artifact changed while it was being published.")
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    if sha256_file(destination) != checksum:
        raise ValueError("Stored artifact failed its content hash check.")
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{attempt_id}/{logical_path}/{checksum}")),
        "experiment_id": experiment_id,
        "attempt_id": attempt_id,
        "sha256": checksum,
        "storage_key": storage_key,
        "name": source.name,
        "relative_path": logical_path,
        "media_type": "chemical/x-mdl-sdfile"
        if source.suffix == ".sdf"
        else (mimetypes.guess_type(source.name)[0] or "application/octet-stream"),
        "size_bytes": destination.stat().st_size,
    }


def verified_path(storage_key: str, checksum: str, size: int) -> Path:
    root = artifact_root()
    path = (root / storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError("The recorded artifact is missing.")
    if path.stat().st_size != size or sha256_file(path) != checksum:
        raise ValueError("The recorded artifact failed its integrity check.")
    return path
