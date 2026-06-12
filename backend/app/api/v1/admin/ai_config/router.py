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
    FreeModeUpdate,
    ProviderConfigUpdate,
    ProviderStatus,
    RoutingRow,
    ScreenModelInfo,
    ScreenOverrideUpdate,
)
from app.services.ai.providers import (
    DEFAULT_PAID_ROUTING,
    FREE_MODEL_OPTIONS,
    FREE_ROUTING,
    PAID_MODEL_OPTIONS,
    SCREEN_DEFAULT_TASK,
    free_fallback_chain,
    model_display_name,
)
from app.services.ai.router import get_ai_router

router = APIRouter(prefix="/admin/ai-config", tags=["admin-ai-config"])


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


def _build_free_routing_rows() -> list[RoutingRow]:
    rows: list[RoutingRow] = []
    for task_type, entry in FREE_ROUTING.items():
        primary_entry = entry.get("model_1", ("openrouter", ""))
        rows.append(
            RoutingRow(
                task_type=task_type,
                task_label=entry.get("task_label", task_type),
                quality_stars=int(entry.get("quality_stars", 4)),
                primary_model=model_display_name(primary_entry[1]),
                fallback_chain=free_fallback_chain(task_type),
                quality_note=entry.get("quality_note"),
            )
        )
    return rows


def _build_response(org: Organization, full: bool = True) -> AiConfigResponse:
    router_svc = get_ai_router()
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
        [
            _provider_status(org, "anthropic"),
            _provider_status(org, "openai"),
            _provider_status(org, "openrouter"),
        ]
        if full
        else [_provider_status(org, "openrouter")]
    )
    return AiConfigResponse(
        free_mode_enabled=org.free_mode_enabled,
        providers=providers,
        paid_routing=_build_paid_routing_rows() if full else [],
        free_routing=_build_free_routing_rows() if full else [],
        screen_overrides=normalized_overrides,
        screen_models=screen_models,
        paid_model_options=PAID_MODEL_OPTIONS,
        free_model_options=FREE_MODEL_OPTIONS,
    )


@router.get("", response_model=AiConfigResponse)
async def get_ai_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.studio_owner, UserRole.studio_admin)),
) -> AiConfigResponse:
    """Return full AI configuration for the admin page."""
    org = await _get_org(db)
    return _build_response(org, full=True)


@router.get("/screen", response_model=AiConfigResponse)
async def get_ai_config_for_screens(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiConfigResponse:
    """Return AI config needed by per-screen model selectors."""
    org = await _get_org(db)
    return _build_response(org, full=False)


@router.patch("/free-mode", response_model=AiConfigResponse)
async def update_free_mode(
    body: FreeModeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.studio_owner, UserRole.studio_admin)),
) -> AiConfigResponse:
    """Enable or disable free mode for the organization."""
    org = await _get_org(db)
    org.free_mode_enabled = body.enabled
    await db.commit()
    await db.refresh(org)
    return _build_response(org, full=True)


@router.post("/use-all-free", response_model=AiConfigResponse)
async def use_all_free(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.studio_owner, UserRole.studio_admin)),
) -> AiConfigResponse:
    """One-click setup: enable free mode and clear paid screen overrides."""
    org = await _get_org(db)
    org.free_mode_enabled = True
    org.screen_model_overrides = {}
    configs = dict(org.ai_provider_configs or {})
    openrouter_cfg = dict(configs.get("openrouter") or {})
    openrouter_cfg["is_enabled"] = True
    configs["openrouter"] = openrouter_cfg
    org.ai_provider_configs = configs
    await db.commit()
    await db.refresh(org)
    return _build_response(org, full=True)


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
    return _build_response(org, full=True)


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
    if body.provider not in ("anthropic", "openai", "openrouter"):
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
    return _build_response(org, full=True)
