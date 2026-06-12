"""Model catalog for the per-action model selection dropdown."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.organization import Organization
from app.services.ai.providers import (
    FREE_MODEL_OPTIONS,
    LOW_COST_MODEL_OPTIONS,
    PAID_MODEL_OPTIONS,
)

router = APIRouter(prefix="/ai", tags=["AI Models"])


def _available_providers(org: Organization | None) -> set[str]:
    settings = get_settings()
    configs = (org.ai_provider_configs if org else None) or {}
    env_map = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "openrouter": settings.openrouter_api_key,
        "groq": settings.groq_api_key,
        "together": settings.together_api_key,
        "gemini": settings.gemini_api_key,
        "cerebras": settings.cerebras_api_key,
        "deepseek": settings.deepseek_api_key,
    }
    available: set[str] = set()
    for provider, env_key in env_map.items():
        cfg = configs.get(provider) or {}
        if cfg.get("api_key") or env_key:
            available.add(provider)
    return available


@router.get("/models")
async def list_models(db: AsyncSession = Depends(get_db)) -> dict:
    """All selectable models grouped for the action dropdown."""
    result = await db.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    available = _available_providers(org)
    tier = getattr(org, "ai_tier", "premium") if org else "premium"

    def decorate(options: list[dict[str, str]], group: str) -> list[dict]:
        return [
            {**opt, "group": group, "available": opt["provider"] in available}
            for opt in options
        ]

    return {
        "default_tier": tier,
        "models": (
            decorate(PAID_MODEL_OPTIONS, "premium")
            + decorate(LOW_COST_MODEL_OPTIONS, "low_cost")
            + decorate(FREE_MODEL_OPTIONS, "free")
        ),
    }
