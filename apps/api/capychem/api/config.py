"""Shared API configuration constants.

Lives in its own module so both main.py (CORS middleware) and ws_runs.py
(WebSocket Origin check) can import it without a circular import — main.py
imports ws_runs' router, so ws_runs cannot import from main.
"""

from __future__ import annotations

import os

# Origins allowed for CORS (HTTP) and for WebSocket handshakes. Note that
# CORSMiddleware does NOT gate WebSocket connections; ws_runs.py enforces
# this list itself on the WS handshake.
ALLOWED_ORIGINS = ["http://localhost:3000"]

# Langfuse deep-link (FR-014 / SPEC §6.3). LANGFUSE_HOST is where the self-hosted
# UI lives; LANGFUSE_PROJECT_ID scopes the trace URL. The project id is not
# derivable from the API keys, so it must be set explicitly — when it is absent
# (or a run has no trace id) there is simply no link, never a broken one.
_DEFAULT_LANGFUSE_HOST = "http://localhost:3001"


def trace_url(trace_id: str | None) -> str | None:
    """Build the Langfuse trace deep link, or None when it cannot be built.

    Returns None (no link) when the run has no trace id or LANGFUSE_PROJECT_ID is
    unconfigured — the UI hides the link in both cases rather than showing a 404.
    """
    project_id = os.environ.get("LANGFUSE_PROJECT_ID")
    if not trace_id or not project_id:
        return None
    host = (os.environ.get("LANGFUSE_HOST") or _DEFAULT_LANGFUSE_HOST).rstrip("/")
    return f"{host}/project/{project_id}/traces/{trace_id}"
