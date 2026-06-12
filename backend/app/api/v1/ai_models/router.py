"""Model catalog for the per-action model selection dropdown."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.organization import Organization
from app.services.ai.model_catalog import build_full_model_catalog, flatten_catalog
from app.services.ai.provider_keys import available_providers

router = APIRouter(prefix="/ai", tags=["AI Models"])


@router.get("/models")
async def list_models(db: AsyncSession = Depends(get_db)) -> dict:
    """All selectable models grouped for the action dropdown."""
    result = await db.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    available = available_providers(org)
    tier = getattr(org, "ai_tier", "premium") if org else "premium"

    catalog = build_full_model_catalog(available)
    models = flatten_catalog(catalog)
    for m in models:
        m["available"] = m["provider"] in available

    return {
        "default_tier": tier,
        "models": models,
    }
