"""CapyChem FastAPI backend.

Slice 1 (walking skeleton) ships only a health check. REST + WebSocket endpoints
and the in-process LangGraph runtime arrive in later slices.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CapyChem API")

# CORS locked to the local web origin (SPEC §8.1) — no wildcards.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
