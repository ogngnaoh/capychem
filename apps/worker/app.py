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

# Lightweight image for the LLM proposer (NOT the harness env). Modern Python +
# a single HTTP client; the DeepSeek API key arrives via a Modal secret.
llm_image = modal.Image.debian_slim(python_version="3.12").pip_install("requests==2.34.2")

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
    raise RuntimeError(f"harness returned no JSON (exit {proc.returncode}): {proc.stderr[-500:]}")


@app.function(
    image=llm_image,
    timeout=300,
    secrets=[modal.Secret.from_name("deepseek-api-key")],
)
def propose(prompt: str, n: int, temperature: float, seed: int, model: str) -> list[dict]:
    """Propose n candidate completions via DeepSeek's OpenAI-compatible API.

    Returns [{raw, tokens_in, tokens_out}] — raw completion text + per-choice
    token usage. SMILES cleaning and USD cost are computed modern-side in
    capychem.proposer. The DEEPSEEK_API_KEY env var is injected by the Modal
    secret; never hard-code or commit it."""
    import os

    import requests

    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "seed": seed,
            # LATENT BUG (deferred, untestable without Modal): DeepSeek caps n=1 per request
            # (400 "Invalid n value"). Mirror capychem.proposer's fan-out fix before using this.
            "n": n,
        },
        timeout=240,
    )
    resp.raise_for_status()
    body = resp.json()
    choices = body["choices"]
    usage = body.get("usage", {})
    # Usage is reported per request; attribute evenly across the n choices.
    per_in = usage.get("prompt_tokens", 0) // max(len(choices), 1)
    per_out = usage.get("completion_tokens", 0) // max(len(choices), 1)
    return [
        {
            "raw": choice["message"]["content"],
            "tokens_in": per_in,
            "tokens_out": per_out,
        }
        for choice in choices
    ]


@app.local_entrypoint()
def smoke() -> None:
    """`modal run apps/worker/app.py` — scores two molecules end to end."""
    out = score.remote(["CCO", "c1ccccc1"], "qed")
    print(out)
    assert len(out) == 2 and all("score" in r for r in out)


@app.local_entrypoint()
def propose_smoke() -> None:
    """`modal run apps/worker/app.py::propose_smoke` — one real DeepSeek call."""
    rows = propose.remote(
        prompt="Propose one drug-like molecule. Output only its SMILES string.",
        n=2,
        temperature=0.7,
        seed=0,
        model="deepseek-v4-pro",
    )
    print(rows)
    assert len(rows) == 2 and all("raw" in r and "tokens_in" in r for r in rows)
