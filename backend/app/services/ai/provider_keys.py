"""Shared provider API key resolution."""

from __future__ import annotations

from app.core.config import get_settings
from app.models.organization import Organization


def provider_env_keys() -> dict[str, str | None]:
    settings = get_settings()
    return {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "openrouter": settings.openrouter_api_key,
        "groq": settings.groq_api_key,
        "together": settings.together_api_key,
        "gemini": settings.gemini_api_key,
        "cerebras": settings.cerebras_api_key,
        "deepseek": settings.deepseek_api_key,
        "sambanova": settings.sambanova_api_key,
        "nvidia": settings.nvidia_api_key,
        "huggingface": settings.huggingface_api_key,
        "aimlapi": settings.aimlapi_api_key,
        "siliconflow": settings.siliconflow_api_key,
        "alibaba": settings.alibaba_api_key,
        "github": settings.github_api_key,
    }


def available_providers(org: Organization | None) -> set[str]:
    env_keys = provider_env_keys()
    configs = (org.ai_provider_configs if org else None) or {}
    available: set[str] = set()
    for provider, env_key in env_keys.items():
        cfg = configs.get(provider) or {}
        if cfg.get("api_key") or env_key:
            available.add(provider)
    return available
