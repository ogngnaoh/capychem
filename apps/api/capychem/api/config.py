"""Shared API configuration constants.

Lives in its own module so both main.py (CORS middleware) and ws_runs.py
(WebSocket Origin check) can import it without a circular import — main.py
imports ws_runs' router, so ws_runs cannot import from main.
"""

from __future__ import annotations

# Origins allowed for CORS (HTTP) and for WebSocket handshakes. Note that
# CORSMiddleware does NOT gate WebSocket connections; ws_runs.py enforces
# this list itself on the WS handshake.
ALLOWED_ORIGINS = ["http://localhost:3000"]
