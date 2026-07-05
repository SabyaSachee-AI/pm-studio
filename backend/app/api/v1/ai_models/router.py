"""Model catalog for the per-action model selection dropdown."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.organization import Organization
from app.services.ai.model_catalog import build_full_model_catalog, flatten_catalog
from app.services.ai.provider_keys import available_providers
from app.services.ai.providers import FREE_ROUTING
from app.services.ai.router import (
    AiRouter,
    _OPENAI_COMPAT_INSTRUCTOR_MODES,
    _is_cooling,
)

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


@router.get("/chain-status")
async def chain_status(
    task_type: str = "code_generate",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Live status of every model in a task's free-tier fallback chain.

    Mirrors scripts/ai_chain_doctor.py for the AI config screen: for each model
    reports whether its provider key is set and whether it is cooling down
    (quota/rate-limit exhausted). A model with no key is silently skipped at
    runtime, so this surfaces where the chain is really shallower than it looks.
    """
    result = await db.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()

    entry = FREE_ROUTING.get(task_type)
    if entry is None:
        return {
            "task_type": task_type,
            "error": "unknown task_type",
            "task_types": sorted(FREE_ROUTING),
            "models": [],
        }

    ar = AiRouter()
    models: list[dict] = []
    idx = 1
    while True:
        pair = entry.get(f"model_{idx}")  # type: ignore[assignment]
        if not pair:
            break
        provider, model = pair
        has_key = org is not None and ar._get_api_key(provider, org) is not None
        supported = (
            provider == "anthropic" or provider in _OPENAI_COMPAT_INSTRUCTOR_MODES
        )
        cooling = await _is_cooling(provider, model) if (has_key and supported) else False
        if not has_key:
            status = "no_key"
        elif not supported:
            status = "unsupported"
        elif cooling:
            status = "cooling"
        else:
            status = "ready"
        models.append({
            "index": idx,
            "provider": provider,
            "model": model,
            "has_key": has_key,
            "cooling": cooling,
            "status": status,
        })
        idx += 1

    usable = sum(1 for m in models if m["status"] == "ready")
    return {
        "task_type": task_type,
        "task_types": sorted(FREE_ROUTING),
        "organization": org.name if org else None,
        "total": len(models),
        "usable_now": usable,
        "models": models,
    }
