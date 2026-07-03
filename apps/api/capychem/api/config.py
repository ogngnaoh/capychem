"""Shared API configuration constants.

Lives in its own module so both main.py (CORS middleware) and ws_runs.py
(WebSocket Origin check) can import it without a circular import — main.py
imports ws_runs' router, so ws_runs cannot import from main.
"""

from __future__ import annotations

import os

# Origins allowed for CORS (HTTP) and for WebSocket handshakes. Note that
# CORSMiddleware does NOT gate WebSocket connections; ws_runs.py enforces
# this list itself on the WS handshake — both read the single list below.
#
# Fork-and-run: a forker on a non-localhost origin sets ALLOWED_ORIGINS to a
# comma-separated list (e.g. "https://app.example.com,https://staging.example.com")
# instead of editing source. Empty/unset falls back to the local dev origin.
_DEFAULT_ORIGINS = ["http://localhost:3000"]


def parse_origins(raw: str | None) -> list[str]:
    """Parse a comma-separated ALLOWED_ORIGINS env value into a clean list.

    Blank/unset yields the local dev default; whitespace and empty entries are
    dropped so "a.com, , b.com," parses to ["a.com", "b.com"].
    """
    if not raw or not raw.strip():
        return list(_DEFAULT_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


ALLOWED_ORIGINS = parse_origins(os.environ.get("ALLOWED_ORIGINS"))

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
