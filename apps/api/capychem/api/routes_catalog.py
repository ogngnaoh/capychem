"""GET /catalog + POST /intent/resolve — the 23-task PMO objective catalog and
grounded intent resolution against the registered task catalog."""

from __future__ import annotations

from capychem.api.catalog import catalog_groups
from capychem.api.intent import resolve_intent
from capychem.api.schemas import CatalogGroupOut, IntentResolution, IntentResolveRequest
from fastapi import APIRouter

router = APIRouter()


@router.get("/catalog", response_model=list[CatalogGroupOut])
def get_catalog() -> list[CatalogGroupOut]:
    return [CatalogGroupOut(**g) for g in catalog_groups()]


@router.post("/intent/resolve", response_model=IntentResolution)
def post_intent_resolve(body: IntentResolveRequest) -> IntentResolution:
    return resolve_intent(body.text, budget=body.budget, seed_smiles=body.seed_smiles)
