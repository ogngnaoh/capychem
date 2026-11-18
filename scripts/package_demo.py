#!/usr/bin/env python3
"""Build a portable, explicitly recorded studio demo with a tiny local server."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = """#!/usr/bin/env python3
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urlencode
import argparse

parser = argparse.ArgumentParser(description="Serve the recorded CapyChem demo locally")
parser.add_argument("--port", type=int, default=5182)
args = parser.parse_args()
class DemoHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        document = url.path in ("/", "/index.html") or (
            "text/html" in self.headers.get("Accept", "") and not Path(url.path).suffix
        )
        query = parse_qs(url.query)
        if document and query.get("mode") != ["demo"]:
            query["mode"] = ["demo"]
            self.send_response(302)
            self.send_header("Location", url.path + "?" + urlencode(query, doseq=True))
            self.end_headers()
            return
        if document:
            self.path = "/index.html"
        super().do_GET()

handler = partial(DemoHandler, directory=str(Path(__file__).resolve().parent))
print(f"CapyChem recorded demo: http://127.0.0.1:{args.port}/?mode=demo", flush=True)
print("No API, model downloads or cloud account are required. Ctrl+C stops the server.")
try:
    ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()
except KeyboardInterrupt:
    pass
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "assets/demo/capychem-studio-demo.zip"
    )
    args = parser.parse_args()
    if not args.skip_build:
        subprocess.run(["pnpm", "build:studio"], cwd=ROOT, check=True)
    source = ROOT / "apps/studio/dist"
    if not (source / "index.html").is_file():
        raise SystemExit("Build the studio first: pnpm build:studio")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="capychem-demo-") as temporary:
        destination = Path(temporary) / "capychem-studio-demo"
        shutil.copytree(source, destination)
        (destination / "serve.py").write_text(SERVER)
        (destination / "START.txt").write_text(
            "CapyChem recorded molecular design workspace\n\n"
            "1. Extract this archive.\n"
            "2. In this folder, run: python3 serve.py\n"
            "3. Open http://127.0.0.1:5182/?mode=demo\n\n"
            "Requires Python 3 and a browser with WebGL. No Node install or API is required.\n"
            "This demo contains real recorded coordinates and evidence; it starts no inference.\n"
            "Use the source repository to configure the live local engine:\n"
            "https://github.com/ogngnaoh/capychem\n"
        )
        shutil.copy2(ROOT / "LICENSE", destination / "LICENSE")
        with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(destination.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(Path(temporary)))
    print(args.output)


if __name__ == "__main__":
    main()
