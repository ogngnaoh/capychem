"""GET /molecule/svg — RDKit 2D depiction, on-token and theme-neutral: a transparent
background plus a single mid-gray stroke color (RDKit writes literal hex, not
``currentColor``, so a neutral gray is the closest theme-agnostic choice) that reads
on both the light and dark workbench themes.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException, Response
from rdkit import Chem, RDLogger
from rdkit.Chem.Draw import rdMolDraw2D

# Silence per-molecule parse warnings; invalidity is signalled by a None mol
# (mirrors packages/core/capychem/validate.py's convention).
RDLogger.DisableLog("rdApp.*")

router = APIRouter()

_MIN_SIZE = 60
_MAX_SIZE = 600
_DEFAULT_SIZE = 220
# tailwind slate-500-ish neutral gray, in RDKit's 0-1 RGB triple.
_NEUTRAL_GRAY = (100 / 255, 116 / 255, 139 / 255)


def _clamp(v: int) -> int:
    return max(_MIN_SIZE, min(_MAX_SIZE, v))


def render_svg(smiles: str, width: int, height: int) -> str:
    """Pure render: caller has already validated ``smiles`` parses."""
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    opts = drawer.drawOptions()
    opts.clearBackground = False  # transparent background
    opts.setAtomPalette({-1: _NEUTRAL_GRAY})  # monochrome, theme-neutral
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    svg: str = drawer.GetDrawingText()
    return svg


@router.get("/molecule/svg")
def molecule_svg(smiles: str, w: int = _DEFAULT_SIZE, h: int = _DEFAULT_SIZE) -> Response:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise HTTPException(status_code=400, detail=f"'{smiles}' is not a valid SMILES string.")
    canon: str = Chem.MolToSmiles(mol)
    width, height = _clamp(w), _clamp(h)
    svg = render_svg(canon, width, height)
    etag = hashlib.sha256(f"{canon}:{width}x{height}".encode()).hexdigest()[:16]
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=604800, immutable",
            "ETag": f'"{etag}"',
        },
    )
