"""The portable archive reproduces the Studio build and serves its recorded deep links."""

import hashlib
import http.client
import importlib.util
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("package_demo", ROOT / "scripts/package_demo.py")
assert spec and spec.loader
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


@pytest.fixture
def studio_build(tmp_path: Path) -> Path:
    build = tmp_path / "studio-dist"
    files = {
        "index.html": b"<html>Studio</html>",
        "THIRD_PARTY_NOTICES.txt": b"App notices",
        "fonts/LICENSE.txt": b"Font notice",
        "data/recorded-experiments.json": b"{}",
        f"data/recorded/{packager.EXPERIMENT}/experiment.json": b"{}",
        f"data/recorded/studies/{packager.STUDY}.json": b"{}",
        "data/pose.sdf": b"Selected coordinates\n$$$$\n",
    }
    for name, contents in files.items():
        path = build / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    return build


def test_same_build_produces_identical_archives_with_offline_notices(
    studio_build: Path, tmp_path: Path
) -> None:
    output = tmp_path / "demo.zip"
    packager.package(studio_build, output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    os.utime(studio_build / "index.html", (1_700_000_000, 1_700_000_000))
    packager.package(studio_build, output)
    assert hashlib.sha256(output.read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name in (
            "LICENSE",
            "THIRD_PARTY_NOTICES.txt",
            "SCIENTIFIC_NOTICES.txt",
            "fonts/LICENSE.txt",
        ):
            assert archive.read(f"{packager.BUNDLE}/{name}")
        start = archive.read(f"{packager.BUNDLE}/START.txt").decode()
        assert f"/experiments/{packager.EXPERIMENT}?mode=demo" in start
        assert f"/studies/{packager.STUDY}?mode=demo" in start


def test_packaged_server_handles_deep_links_assets_and_head(
    studio_build: Path, tmp_path: Path
) -> None:
    output = tmp_path / "demo.zip"
    packager.package(studio_build, output)
    with zipfile.ZipFile(output) as archive:
        archive.extractall(tmp_path)
    app = tmp_path / packager.BUNDLE
    server = subprocess.Popen(
        [sys.executable, str(app / "serve.py"), "--port", "0"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert server.stdout
        address = urlsplit(server.stdout.readline().strip())
        assert address.hostname == "127.0.0.1" and address.port
        conn = http.client.HTTPConnection(address.hostname, address.port, timeout=5)
        try:
            experiment_route = f"/experiments/{packager.EXPERIMENT}"
            study_route = f"/studies/{packager.STUDY}"
            conn.request("GET", experiment_route + "?pose=one&mode=live")
            response = conn.getresponse()
            assert response.status == 302
            assert response.getheader("Location") == experiment_route + "?pose=one&mode=demo"
            response.read()
            for route in (experiment_route + "/activity", study_route):
                conn.request("GET", route + "?mode=demo")
                response = conn.getresponse()
                assert response.status == 200
                assert response.read() == (app / "index.html").read_bytes()
            conn.request("HEAD", study_route + "?mode=demo")
            response = conn.getresponse()
            assert response.status == 200 and response.read() == b""
            conn.request("GET", "/data/pose.sdf")
            assert conn.getresponse().read() == (app / "data/pose.sdf").read_bytes()
            conn.request("GET", "/api/experiments")
            response = conn.getresponse()
            assert response.status == 404
            response.read()
        finally:
            conn.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
