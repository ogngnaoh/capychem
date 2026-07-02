"""GET /molecule/svg — RDKit 2D depiction (milestone 05 slice 03a)."""

from __future__ import annotations

import httpx
from capychem.api.main import app
from httpx_ws.transport import ASGIWebSocketTransport


async def test_molecule_svg_valid_smiles_returns_svg() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r = await c.get("/molecule/svg", params={"smiles": "c1ccccc1"})
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("image/svg+xml")
            assert "Cache-Control" in r.headers
            assert "ETag" in r.headers
            assert r.text.strip().startswith("<?xml")


async def test_molecule_svg_invalid_smiles_400() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r = await c.get("/molecule/svg", params={"smiles": "not a smiles!!"})
            assert r.status_code == 400
            assert "not a valid SMILES" in r.json()["detail"]


async def test_molecule_svg_default_size_is_220() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r = await c.get("/molecule/svg", params={"smiles": "c1ccccc1"})
            assert "width='220px'" in r.text
            assert "height='220px'" in r.text


async def test_molecule_svg_respects_w_h_and_bounds_size() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r = await c.get("/molecule/svg", params={"smiles": "c1ccccc1", "w": 100, "h": 100})
            assert "width='100px'" in r.text

            # oversized request is clamped, not rejected
            r2 = await c.get("/molecule/svg", params={"smiles": "c1ccccc1", "w": 99999, "h": 99999})
            assert r2.status_code == 200
            assert "width='600px'" in r2.text


async def test_molecule_svg_same_smiles_same_etag() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as c:
            r1 = await c.get("/molecule/svg", params={"smiles": "c1ccccc1"})
            r2 = await c.get("/molecule/svg", params={"smiles": "C1=CC=CC=C1"})  # same molecule
            assert r1.headers["ETag"] == r2.headers["ETag"]  # canonicalized before hashing
