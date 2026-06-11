"""Modal worker: PMO oracle scoring (slice 4).

The image IS the legacy harness env (Python 3.10 + PyTDC 0.3.6). The harness
import/exec happens only inside the remote function body, never at module load —
so this file stays importable under modern Python 3.12 when Modal parses it.
The function shells out to the UNCHANGED harness/capychem_harness/score.py, the
same stdin/stdout JSON contract used locally, relocated into the container.

# verified against modal 1.5.0 (installed via apps/api dep). Version-sensitive
# calls reconciled against the installed API:
#   - Image.add_local_dir(local_path, remote_path, *, copy=False, ...): remote_path
#     is positional; copy=True bakes the dir into a build-time image layer (Dockerfile
#     COPY-like) so harness/capychem_harness is present when the function runs and the
#     subprocess shellout resolves /root/capychem_harness/score.py.
#   - App(name), @app.function(image=, timeout=), @app.local_entrypoint(),
#     Image.debian_slim(python_version=), Image.pip_install(*pkgs) all unchanged.
#   - Async call surface fn.remote.aio(...) (used by capychem.oracle) still valid in
#     1.5.0 — Function.remote exposes .aio for the async variant.
"""
from __future__ import annotations

import modal

# Pinned to the EXACT versions frozen in harness/uv.lock (the proven legacy env)
# so the image == the legacy harness env and future builds are deterministic.
# PyTDC 0.3.6 has incomplete metadata, so requests/networkx/scipy/numpy are
# declared explicitly (CLAUDE.md gotcha).
# NO rdkit.six shim is needed here: score.py installs its own runtime sys.modules
# shim when executed (harness/capychem_harness/score.py) — we just ship + run it.
image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "PyTDC==0.3.6",
        "rdkit==2026.3.2",
        "requests==2.34.2",
        "networkx==3.4.2",
        "scipy==1.15.3",
        "numpy==2.2.6",
    )
    .add_local_dir("harness/capychem_harness", "/root/capychem_harness", copy=True)
)

app = modal.App("capychem-worker")


@app.function(image=image, timeout=300)
def score(smiles: list[str], task: str) -> list[dict]:
    """Score SMILES against a PyTDC oracle inside the 3.10 container.

    Returns [{smiles, score, valid, wall_ms}] — mirrors OracleResult minus cost
    (cost policy lives modern-side in capychem.oracle)."""
    import json
    import subprocess
    import sys

    request = json.dumps({"task": task, "smiles": smiles})
    proc = subprocess.run(
        [sys.executable, "/root/capychem_harness/score.py"],
        input=request,
        capture_output=True,
        text=True,
        timeout=240,
    )
    for line in reversed(proc.stdout.strip().splitlines()):
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"harness error scoring task {task!r}: {payload['error']}")
        if isinstance(payload, dict) and "results" in payload:
            return payload["results"]
    raise RuntimeError(
        f"harness returned no JSON (exit {proc.returncode}): {proc.stderr[-500:]}"
    )


@app.local_entrypoint()
def smoke() -> None:
    """`modal run apps/worker/app.py` — scores two molecules end to end."""
    out = score.remote(["CCO", "c1ccccc1"], "qed")
    print(out)
    assert len(out) == 2 and all("score" in r for r in out)
