"""Admin AI configuration endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.ai_config import (
    AiConfigResponse,
    AiTierUpdate,
    FreeModeUpdate,
    ProviderConfigUpdate,
    ProviderStatus,
    ProviderUsage,
    RoutingRow,
    ScreenModelInfo,
    ScreenOverrideUpdate,
)
from app.services.ai.providers import (
    ALL_PROVIDERS,
    DEFAULT_PAID_ROUTING,
    FREE_MODEL_OPTIONS,
    FREE_ROUTING,
    LOW_COST_MODEL_OPTIONS,
    LOW_COST_ROUTING,
    PAID_MODEL_OPTIONS,
    SCREEN_DEFAULT_TASK,
    chain_fallback_summary,
    free_fallback_chain,
    low_cost_fallback_chain,
    model_display_name,
)
from app.services.ai.router import get_ai_router
from app.services.ai.usage_tracker import PROVIDER_DAILY_LIMITS, get_daily_usage

router = APIRouter(prefix="/admin/ai-config", tags=["admin-ai-config"])

_VALID_TIERS = frozenset({"free", "low_cost", "premium"})


async def _get_org(db: AsyncSession) -> Organization:
    result = await db.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return f"{key[:7]}...{key[-4:]}"


def _provider_status(org: Organization, provider: str) -> ProviderStatus:
    settings = get_settings()
    configs = org.ai_provider_configs or {}
    cfg = configs.get(provider) or {}
    env_keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "openrouter": settings.openrouter_api_key,
        "groq": settings.groq_api_key,
        "together": settings.together_api_key,
        "gemini": settings.gemini_api_key,
        "cerebras": settings.cerebras_api_key,
        "deepseek": settings.deepseek_api_key,
    }
    api_key = cfg.get("api_key") or env_keys.get(provider)
    configured = bool(api_key)
    is_enabled = cfg.get("is_enabled", configured)
    return ProviderStatus(
        provider=provider,
        configured=configured,
        is_enabled=bool(is_enabled and configured),
        masked_key=_mask_key(api_key),
    )


def _build_paid_routing_rows() -> list[RoutingRow]:
    rows: list[RoutingRow] = []
    for task_type, (_provider, model) in DEFAULT_PAID_ROUTING.items():
        rows.append(
            RoutingRow(
                task_type=task_type,
                task_label=task_type.replace("_", " ").title(),
                quality_stars=5 if "sonnet" in model else 4,
                primary_model=model_display_name(model),
                fallback_chain="OpenAI GPT-4o" if _provider == "anthropic" else "",
                quality_note=None,
            )
        )
    return rows


def _build_tier_routing_rows(
    routing_table: dict[str, dict],
    fallback_fn,
) -> list[RoutingRow]:
    rows: list[RoutingRow] = []
    for task_type, entry in routing_table.items():
        primary_entry = entry.get("model_1", ("openrouter", ""))
        rows.append(
            RoutingRow(
                task_type=task_type,
                task_label=entry.get("task_label", task_type),
                quality_stars=int(entry.get("quality_stars", 4)),
                primary_model=model_display_name(primary_entry[1]),
                fallback_chain=fallback_fn(task_type) or chain_fallback_summary(entry),
                quality_note=entry.get("quality_note"),
            )
        )
    return rows


async def _build_daily_usage(org: Organization) -> dict[str, ProviderUsage]:
    raw = await get_daily_usage(str(org.id))
    result: dict[str, ProviderUsage] = {}
    for provider, limits in PROVIDER_DAILY_LIMITS.items():
        usage = raw.get(provider, {"requests": 0, "tokens_in": 0, "tokens_out": 0})
        req_limit = int(limits.get("requests_per_day") or 0)
        tok_limit = int(limits.get("tokens_per_day") or 0)
        result[provider] = ProviderUsage(
            requests=usage.get("requests", 0),
            tokens_in=usage.get("tokens_in", 0),
            tokens_out=usage.get("tokens_out", 0),
            requests_limit=req_limit,
            tokens_limit=tok_limit,
            label=str(limits.get("label", provider)),
            color=str(limits.get("color", "gray")),
        )
    return result


async def _build_response(org: Organization, full: bool = True) -> AiConfigResponse:
    router_svc = get_ai_router()
    tier = getattr(org, "ai_tier", None) or ("free" if org.free_mode_enabled else "premium")
    if tier not in _VALID_TIERS:
        tier = "free" if org.free_mode_enabled else "premium"

    screen_models = [
        ScreenModelInfo(
            screen=screen,
            **router_svc.resolve_screen_model(org, screen),
        )
        for screen in SCREEN_DEFAULT_TASK
    ]
    overrides = org.screen_model_overrides or {}
    normalized_overrides = {
        k: v for k, v in overrides.items() if isinstance(v, dict)
    }
    providers = (
        [_provider_status(org, p) for p in ALL_PROVIDERS]
        if full
        else [_provider_status(org, "openrouter")]
    )
    daily_usage = await _build_daily_usage(org) if full else {}

    return AiConfigResponse(
        ai_tier=tier,
        free_mode_enabled=org.free_mode_enabled,
        providers=providers,
        paid_routing=_build_paid_routing_rows() if full else [],
        free_routing=_build_tier_routing_rows(FREE_ROUTING, free_fallback_chain)
        if full
        else [],
        low_cost_routing=_build_tier_routing_rows(
            LOW_COST_ROUTING, low_cost_fallback_chain
        )
        if full
        else [],
        screen_overrides=normalized_overrides,
        screen_models=screen_models,
        paid_model_options=PAID_MODEL_OPTIONS,
        free_model_options=FREE_MODEL_OPTIONS,
        low_cost_model_options=LOW_COST_MODEL_OPTIONS,
        daily_usage=daily_usage,
    )


def _sync_tier_flags(org: Organization, tier: str) -> None:
    org.ai_tier = tier
    org.free_mode_enabled = tier == "free"


@router.get("", response_model=AiConfigResponse)
async def get_ai_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.studio_owner, UserRole.studio_admin)),
) -> AiConfigResponse:
    """Return full AI configuration for the admin page."""
    org = await _get_org(db)
    return await _build_response(org, full=True)


@router.get("/screen", response_model=AiConfigResponse)
async def get_ai_config_for_screens(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiConfigResponse:
    """Return AI config needed by per-screen model selectors."""
    org = await _get_org(db)
    return await _build_response(org, full=False)


@router.patch("/tier", response_model=AiConfigResponse)
async def update_ai_tier(
    body: AiTierUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.studio_owner, UserRole.studio_admin)),
) -> AiConfigResponse:
    """Set organization AI cost tier: free | low_cost | premium."""
    if body.tier not in _VALID_TIERS:
        raise HTTPException(status_code=400, detail="tier must be free, low_cost, or premium")
    org = await _get_org(db)
    _sync_tier_flags(org, body.tier)
    await db.commit()
    await db.refresh(org)
    return await _build_response(org, full=True)


@router.patch("/free-mode", response_model=AiConfigResponse)
async def update_free_mode(
    body: FreeModeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.studio_owner, UserRole.studio_admin)),
) -> AiConfigResponse:
    """Enable or disable free mode (legacy — sets ai_tier to free or premium)."""
    org = await _get_org(db)
    _sync_tier_flags(org, "free" if body.enabled else "premium")
    await db.commit()
    await db.refresh(org)
    return await _build_response(org, full=True)


@router.post("/use-all-free", response_model=AiConfigResponse)
async def use_all_free(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.studio_owner, UserRole.studio_admin)),
) -> AiConfigResponse:
    """One-click setup: free tier + clear paid screen overrides."""
    org = await _get_org(db)
    _sync_tier_flags(org, "free")
    org.screen_model_overrides = {}
    configs = dict(org.ai_provider_configs or {})
    for prov in ("openrouter", "groq", "gemini"):
        prov_cfg = dict(configs.get(prov) or {})
        if prov_cfg.get("api_key") or prov == "openrouter":
            prov_cfg["is_enabled"] = True
        configs[prov] = prov_cfg
    org.ai_provider_configs = configs
    await db.commit()
    await db.refresh(org)
    return await _build_response(org, full=True)


@router.patch("/screen-override", response_model=AiConfigResponse)
async def update_screen_override(
    body: ScreenOverrideUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiConfigResponse:
    """Set or clear a per-screen model override."""
    if body.screen not in SCREEN_DEFAULT_TASK:
        raise HTTPException(status_code=400, detail=f"Unknown screen: {body.screen}")

    org = await _get_org(db)
    overrides = dict(org.screen_model_overrides or {})

    if not body.provider or not body.model:
        overrides.pop(body.screen, None)
    else:
        overrides[body.screen] = {
            "provider": body.provider,
            "model": body.model,
        }

    org.screen_model_overrides = overrides
    await db.commit()
    await db.refresh(org)
    return await _build_response(org, full=True)


@router.get("/screen-overrides")
async def get_screen_overrides(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.studio_owner, UserRole.studio_admin)),
) -> dict[str, Any]:
    """Return all screen-level model overrides."""
    org = await _get_org(db)
    return org.screen_model_overrides or {}


@router.patch("/provider", response_model=AiConfigResponse)
async def update_provider_config(
    body: ProviderConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.studio_owner, UserRole.studio_admin)),
) -> AiConfigResponse:
    """Update provider API key and enabled flag."""
    if body.provider not in ALL_PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider")

    org = await _get_org(db)
    configs = dict(org.ai_provider_configs or {})
    existing = dict(configs.get(body.provider) or {})

    if body.api_key is not None:
        existing["api_key"] = body.api_key
    if body.is_enabled is not None:
        existing["is_enabled"] = body.is_enabled
    elif body.api_key:
        existing["is_enabled"] = True

    configs[body.provider] = existing
    org.ai_provider_configs = configs
    await db.commit()
    await db.refresh(org)
    return await _build_response(org, full=True)
