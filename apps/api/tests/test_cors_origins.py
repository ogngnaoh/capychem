"""ALLOWED_ORIGINS is env-driven and drives both CORS and the WS Origin check.

A single parsed list in config.py is imported by main.py (CORSMiddleware) and
ws_runs.py (manual WS handshake check); a forker sets one env var, not source.
"""

from __future__ import annotations

from capychem.api.config import parse_origins


def test_unset_falls_back_to_local_dev() -> None:
    assert parse_origins(None) == ["http://localhost:3000"]
    assert parse_origins("") == ["http://localhost:3000"]
    assert parse_origins("   ") == ["http://localhost:3000"]


def test_comma_separated_list_is_parsed() -> None:
    assert parse_origins("https://a.example.com,https://b.example.com") == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_whitespace_and_empty_entries_are_dropped() -> None:
    assert parse_origins("https://a.com, , https://b.com,") == [
        "https://a.com",
        "https://b.com",
    ]


def test_main_and_ws_read_the_same_list() -> None:
    # Both enforcement sites import the module-level ALLOWED_ORIGINS object, so
    # one env-parsed list gates HTTP CORS and the WS handshake identically.
    from capychem.api import config, main, ws_runs

    assert main.ALLOWED_ORIGINS is config.ALLOWED_ORIGINS
    assert ws_runs.ALLOWED_ORIGINS is config.ALLOWED_ORIGINS
