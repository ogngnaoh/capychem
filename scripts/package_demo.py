#!/usr/bin/env python3
"""Package the Studio production build and its recorded experiments for offline use."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "capychem-studio-demo"
EXPERIMENT = "58c63b90-086a-4cb6-adee-e09657734574"
STUDY = "a73fc517-6425-490a-a921-9ea3e7c0686d"

START = f"""CapyChem recorded workspace

1. Extract the archive. In the folder containing serve.py, run:
   python3 serve.py

2. Open the experiment to compare two molecules in a protein pocket:
   http://127.0.0.1:5182/experiments/{EXPERIMENT}?mode=demo

3. Open the study to compare results across three sampling seeds:
   http://127.0.0.1:5182/studies/{STUDY}?mode=demo

The demo needs Python 3 and a browser with WebGL. All scientific data, fonts
and application files are included. It serves recorded results on your
computer. Ctrl+C stops the server. Use --port to choose another port.

LICENSE, THIRD_PARTY_NOTICES.txt, SCIENTIFIC_NOTICES.txt and fonts/LICENSE.txt
describe the code, data and fonts in this distribution.
"""

SERVER = """#!/usr/bin/env python3
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit


class DemoHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        url = urlsplit(self.path)
        root = url.path.strip("/").split("/", 1)[0]
        # Direct links and refreshes of client routes load the same recorded app.
        if url.path in ("/", "/index.html") or root in (
            "experiments", "studies", "engine", "help", "references"
        ):
            query = parse_qs(url.query, keep_blank_values=True)
            if query.get("mode") != ["demo"]:
                query["mode"] = ["demo"]
                self.send_response(302)
                self.send_header("Location", url.path + "?" + urlencode(query, doseq=True))
                self.end_headers()
                return None
            self.path = "/index.html"
        return super().send_head()


parser = argparse.ArgumentParser(description="Serve the recorded CapyChem workspace")
parser.add_argument("--port", type=int, default=5182)
args = parser.parse_args()
handler = partial(DemoHandler, directory=str(Path(__file__).resolve().parent))
with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
    print(f"http://127.0.0.1:{server.server_port}/?mode=demo", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
"""


def package(source: Path, output: Path) -> None:
    for relative in (
        "index.html",
        "THIRD_PARTY_NOTICES.txt",
        "fonts/LICENSE.txt",
        "data/recorded-experiments.json",
        f"data/recorded/{EXPERIMENT}/experiment.json",
        f"data/recorded/studies/{STUDY}.json",
    ):
        if not (source / relative).is_file():
            raise SystemExit(f"Studio build is missing {relative}. Run pnpm build:studio.")

    if output.resolve().is_relative_to(source.resolve()):
        raise SystemExit("Choose an output path outside the Studio build directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    extras = {
        "serve.py": SERVER.encode(),
        "START.txt": START.encode(),
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
        "SCIENTIFIC_NOTICES.txt": (
            ROOT / "data/reference/cdk2/THIRD_PARTY_NOTICES.txt"
        ).read_bytes(),
    }
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        staging = Path(temporary) / "demo.zip"
        with zipfile.ZipFile(staging, "w") as archive:
            files = {p.relative_to(source).as_posix(): p for p in source.rglob("*") if p.is_file()}
            for name in sorted(files.keys() | extras.keys()):
                data = extras[name] if name in extras else files[name].read_bytes()
                # Fixed metadata makes the same build byte-identical after copying or unpacking it.
                entry = zipfile.ZipInfo(f"{BUNDLE}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        staging.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="Package the current Studio dist")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / f"{BUNDLE}.zip")
    args = parser.parse_args()
    studio = ROOT / "apps/studio"
    if not args.skip_build:
        subprocess.run(["pnpm", "--dir", str(studio), "build"], cwd=ROOT, check=True)
    package(studio / "dist", args.output)
    print(args.output)


if __name__ == "__main__":
    main()
