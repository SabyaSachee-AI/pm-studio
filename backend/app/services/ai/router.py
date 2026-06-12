"""AI routing: free / low_cost / premium tiers, multi-provider chains, screen overrides."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Type, TypeVar
from uuid import UUID

import httpx
import instructor
from anthropic import AsyncAnthropic, RateLimitError as AnthropicRateLimitError
from openai import (
    APIStatusError,
    AsyncOpenAI,
    RateLimitError as OpenAIRateLimitError,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SyncSessionLocal
from app.models.organization import Organization
from app.services.ai.providers import (
    DEFAULT_PAID_ROUTING,
    FREE_MODE_QUALITY_BOOSTS,
    LOW_COST_ROUTING,
    FREE_ROUTING,
    SCREEN_DEFAULT_TASK,
    model_display_name,
    routing_for_tier,
)
from app.services.ai.model_override import get_model_override
from app.services.ai.usage_tracker import increment_usage

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

_RATE_LIMIT_ERRORS = (AnthropicRateLimitError, OpenAIRateLimitError, APIStatusError)

_ARCH_TASK_TIMEOUT_SEC = 720
_DEFAULT_TASK_TIMEOUT_SEC = 300
_HTTP_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=60.0, pool=30.0)

_ARCH_MAX_RETRIES = 2
_DEFAULT_MAX_RETRIES = 3

_COOLDOWN_DAILY_QUOTA_SEC = 3600
_COOLDOWN_RATE_LIMIT_SEC = 120

_PROVIDER_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "cerebras": "https://api.cerebras.ai/v1",
    "deepseek": "https://api.deepseek.com",
}

_OPENAI_COMPAT_INSTRUCTOR_MODES: dict[str, instructor.Mode] = {
    "openai": instructor.Mode.JSON,
    "openrouter": instructor.Mode.JSON,
    "groq": instructor.Mode.TOOLS,
    "together": instructor.Mode.JSON,
    "gemini": instructor.Mode.JSON,
    "cerebras": instructor.Mode.JSON,
    "deepseek": instructor.Mode.JSON,
}

_PROVIDER_OUTPUT_CAPS: dict[str, int] = {
    "groq": 8192,
    "cerebras": 8192,
    "deepseek": 8192,
}


def _effective_max_tokens(provider: str, requested: int, task_type: str) -> int:
    """Clamp max_tokens per provider limits (Groq 8192, Gemini higher for arch)."""
    cap = _PROVIDER_OUTPUT_CAPS.get(provider, requested)
    if provider == "gemini" and task_type.startswith("arch_"):
        cap = max(cap, 24000)
    return min(requested, cap)


def _resolve_effective_tier(org: Organization) -> str:
    """Return active cost tier; sync legacy free_mode_enabled flag."""
    tier = getattr(org, "ai_tier", None) or "premium"
    if tier not in ("free", "low_cost", "premium"):
        tier = "free" if org.free_mode_enabled else "premium"
    if org.free_mode_enabled and tier == "premium":
        tier = "free"
    return tier


def _is_rate_limit_error(exc: BaseException) -> bool:
    if isinstance(exc, _RATE_LIMIT_ERRORS):
        if isinstance(exc, APIStatusError) and exc.status_code not in (429, 503):
            return False
        return True
    msg = str(exc).lower()
    return "rate limit" in msg or "429" in msg or "quota" in msg or "503" in msg


def _is_daily_quota_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "quota" in msg
        or "resource_exhausted" in msg
        or "exceeded your current quota" in msg
        or "daily" in msg
    )


async def _is_cooling(provider: str, model: str) -> bool:
    try:
        import redis.asyncio as redis  # type: ignore[import]

        from app.core.config import get_settings

        settings = get_settings()
        r = redis.from_url(settings.redis_url, decode_responses=True)
        async with r:
            if await r.exists(f"ai_cooldown:{provider}"):
                return True
            return bool(await r.exists(f"ai_cooldown:{provider}:{model}"))
    except Exception:
        return False


async def _set_cooling(
    provider: str,
    model: str,
    seconds: int,
    scope: str,
) -> None:
    try:
        import redis.asyncio as redis  # type: ignore[import]

        from app.core.config import get_settings

        settings = get_settings()
        key = (
            f"ai_cooldown:{provider}"
            if scope == "provider"
            else f"ai_cooldown:{provider}:{model}"
        )
        r = redis.from_url(settings.redis_url, decode_responses=True)
        async with r:
            await r.setex(key, seconds, "1")
    except Exception as exc:
        logger.debug("Cooldown set failed (non-fatal): %s", exc)


def _task_timeout_sec(task_type: str) -> float:
    if task_type.startswith("arch_"):
        return float(_ARCH_TASK_TIMEOUT_SEC)
    return float(_DEFAULT_TASK_TIMEOUT_SEC)


class AiRouter:
    """Route AI calls through tier chains, paid defaults, or screen overrides."""

    async def call(
        self,
        task_type: str,
        prompt: str,
        response_model: Type[T],
        system: str = "",
        context: str = "",
        max_tokens: int = 4000,
        screen: str | None = None,
        screen_override: tuple[str, str] | None = None,
        org_id: UUID | None = None,
        db: AsyncSession | None = None,
    ) -> T:
        org = await self._resolve_org(org_id, db)
        tier = _resolve_effective_tier(org)

        request_override = get_model_override()
        override = screen_override or request_override
        if override is None and screen and org.screen_model_overrides:
            raw = org.screen_model_overrides.get(screen)
            if raw and isinstance(raw, dict):
                provider = raw.get("provider")
                model = raw.get("model")
                if provider and model:
                    override = (provider, model)

        if override:
            provider, model = override
            return await self._call_with_retry(
                provider,
                model,
                prompt,
                response_model,
                system,
                context,
                max_tokens,
                task_type,
                org,
                tier=tier,
            )

        if tier in ("free", "low_cost"):
            routing_table = routing_for_tier(tier)
            routing = routing_table.get(task_type)
            if not routing:
                raise ValueError(f"No {tier} routing defined for task: {task_type}")
            enhanced_prompt = prompt
            if task_type in FREE_MODE_QUALITY_BOOSTS:
                enhanced_prompt = (
                    f"{FREE_MODE_QUALITY_BOOSTS[task_type].strip()}\n\n{prompt}"
                )
            return await self._try_chain(
                routing,
                enhanced_prompt,
                response_model,
                system,
                context,
                max_tokens,
                task_type,
                org,
                tier=tier,
            )

        provider, model = DEFAULT_PAID_ROUTING.get(
            task_type, ("anthropic", "claude-sonnet-4-5")
        )
        return await self._call_with_retry(
            provider,
            model,
            prompt,
            response_model,
            system,
            context,
            max_tokens,
            task_type,
            org,
            tier="premium",
        )

    async def _resolve_org(
        self,
        org_id: UUID | None,
        db: AsyncSession | None,
    ) -> Organization:
        if db is not None:
            if org_id is not None:
                result = await db.execute(
                    select(Organization).where(Organization.id == org_id)
                )
                org = result.scalar_one_or_none()
                if org is not None:
                    return org
            result = await db.execute(select(Organization).limit(1))
            org = result.scalar_one_or_none()
            if org is not None:
                return org
        return self._get_default_org_sync()

    def _get_default_org_sync(self) -> Organization:
        with SyncSessionLocal() as session:
            org = session.execute(select(Organization).limit(1)).scalar_one_or_none()
            if org is None:
                raise RuntimeError("No organization configured")
            return org

    def _get_api_key(self, provider: str, org: Organization) -> str | None:
        settings = get_settings()
        configs = org.ai_provider_configs or {}
        provider_cfg = configs.get(provider) or {}
        if provider_cfg.get("api_key"):
            return provider_cfg["api_key"]
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
        return env_map.get(provider)

    def _provider_enabled(self, provider: str, org: Organization) -> bool:
        configs = org.ai_provider_configs or {}
        provider_cfg = configs.get(provider) or {}
        if provider_cfg.get("is_enabled") is False:
            return False
        return self._get_api_key(provider, org) is not None

    async def _try_chain(
        self,
        routing: dict[str, Any],
        prompt: str,
        response_model: Type[T],
        system: str,
        context: str,
        max_tokens: int,
        task_type: str,
        org: Organization,
        tier: str,
    ) -> T:
        models_in_chain: list[tuple[str, str]] = []
        for attempt_num in range(1, 16):
            entry = routing.get(f"model_{attempt_num}")
            if entry:
                models_in_chain.append(entry)

        if not models_in_chain:
            raise RuntimeError(f"Empty model chain for {task_type}, tier={tier}")

        last_error: str | None = None
        timeout_sec = _task_timeout_sec(task_type)

        for attempt_num, (provider, model) in enumerate(models_in_chain, start=1):
            if await _is_cooling(provider, model):
                last_error = f"Cooling down: {provider}/{model}"
                logger.info(
                    "Skipping %s/%s — cooling down",
                    provider,
                    model,
                    extra={"tier": tier, "attempt": attempt_num},
                )
                continue

            if not self._provider_enabled(provider, org):
                logger.debug(
                    "Skipping %s/%s — not configured",
                    provider,
                    model,
                    extra={"tier": tier, "attempt": attempt_num},
                )
                continue

            mode = _OPENAI_COMPAT_INSTRUCTOR_MODES.get(provider)
            if provider != "anthropic" and mode is None:
                logger.debug("Skipping %s — unsupported provider", provider)
                continue

            api_key = self._get_api_key(provider, org) or ""
            effective_tokens = _effective_max_tokens(provider, max_tokens, task_type)

            try:
                call_coro = self._call_provider(
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    prompt=prompt,
                    response_model=response_model,
                    system=system,
                    context=context,
                    max_tokens=effective_tokens,
                    task_type=task_type,
                )
                result = await asyncio.wait_for(call_coro, timeout=timeout_sec)
                await self._log_usage(
                    task_type=task_type,
                    provider=provider,
                    model=model,
                    org_id=org.id,
                    tier=tier,
                    attempt_number=attempt_num,
                )
                return result
            except asyncio.TimeoutError:
                last_error = f"Timeout after {timeout_sec}s: {provider}/{model}"
                logger.warning(last_error, extra={"tier": tier, "attempt": attempt_num})
                continue
            except Exception as exc:
                is_rate_limit = _is_rate_limit_error(exc)
                last_error = (
                    f"Rate limit: {provider}/{model}"
                    if is_rate_limit
                    else str(exc)[:200]
                )
                if is_rate_limit:
                    if _is_daily_quota_error(exc):
                        await _set_cooling(
                            provider,
                            model,
                            _COOLDOWN_DAILY_QUOTA_SEC,
                            "provider",
                        )
                    else:
                        await _set_cooling(
                            provider,
                            model,
                            _COOLDOWN_RATE_LIMIT_SEC,
                            "model",
                        )
                    logger.warning(
                        "Rate limited on %s/%s — switching model",
                        provider,
                        model,
                        extra={"tier": tier},
                    )
                    await asyncio.sleep(1)
                else:
                    logger.exception(
                        "Model failed, trying next",
                        extra={
                            "provider": provider,
                            "model": model,
                            "tier": tier,
                            "attempt": attempt_num,
                        },
                    )
                continue

        raise RuntimeError(
            f"All models failed for {task_type}, tier={tier}. "
            f"Last error: {last_error}. "
            "Try again later or switch tier."
        )

    async def _call_with_retry(
        self,
        provider: str,
        model: str,
        prompt: str,
        response_model: Type[T],
        system: str,
        context: str,
        max_tokens: int,
        task_type: str,
        org: Organization,
        tier: str,
    ) -> T:
        api_key = self._get_api_key(provider, org)
        if not api_key:
            if provider == "openai" and self._get_api_key("anthropic", org):
                provider, model = "anthropic", "claude-sonnet-4-5"
                api_key = self._get_api_key("anthropic", org)
            elif provider == "anthropic" and self._get_api_key("openai", org):
                provider, model = "openai", "gpt-4o"
                api_key = self._get_api_key("openai", org)
            else:
                raise RuntimeError(f"{provider} API key not configured")

        effective_tokens = _effective_max_tokens(provider, max_tokens, task_type)
        result = await self._call_provider(
            provider=provider,
            model=model,
            api_key=api_key or "",
            prompt=prompt,
            response_model=response_model,
            system=system,
            context=context,
            max_tokens=effective_tokens,
            task_type=task_type,
        )
        await self._log_usage(
            task_type=task_type,
            provider=provider,
            model=model,
            org_id=org.id,
            tier=tier,
            attempt_number=1,
        )
        return result

    async def _call_provider(
        self,
        provider: str,
        model: str,
        api_key: str,
        prompt: str,
        response_model: Type[T],
        system: str,
        context: str,
        max_tokens: int,
        task_type: str = "req_analyze",
    ) -> T:
        system_msg = system or "You are a professional software engineering assistant."
        messages = _build_openai_messages(prompt, context, system_msg)

        max_retries = (
            _ARCH_MAX_RETRIES
            if task_type.startswith("arch_")
            else _DEFAULT_MAX_RETRIES
        )

        if provider == "anthropic":
            client = instructor.from_anthropic(AsyncAnthropic(api_key=api_key))
            return await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_msg,
                messages=_build_anthropic_messages(prompt, context),
                response_model=response_model,
                max_retries=max_retries,
            )

        if provider in _OPENAI_COMPAT_INSTRUCTOR_MODES:
            base_url = _PROVIDER_BASE_URLS.get(provider)
            default_headers = None
            if provider == "openrouter":
                default_headers = {
                    "HTTP-Referer": "https://pmstudio.app",
                    "X-Title": "PM Studio",
                }
            raw_client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=_HTTP_TIMEOUT,
                default_headers=default_headers,
            )
            mode = _OPENAI_COMPAT_INSTRUCTOR_MODES[provider]
            client = instructor.from_openai(raw_client, mode=mode)
            return await client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                response_model=response_model,
                max_retries=max_retries,
            )

        raise ValueError(f"Unsupported provider: {provider}")

    async def _log_usage(
        self,
        task_type: str,
        provider: str,
        model: str,
        org_id: UUID,
        tier: str,
        attempt_number: int,
    ) -> None:
        logger.info(
            "AI usage",
            extra={
                "task_type": task_type,
                "provider": provider,
                "model": model,
                "org_id": str(org_id),
                "tier": tier,
                "attempt": attempt_number,
            },
        )
        await increment_usage(str(org_id), provider)

    def resolve_screen_model(
        self,
        org: Organization,
        screen: str,
    ) -> dict[str, str]:
        """Return effective provider/model label for a screen."""
        overrides = org.screen_model_overrides or {}
        raw = overrides.get(screen)
        if raw and isinstance(raw, dict) and raw.get("provider") and raw.get("model"):
            return {
                "provider": raw["provider"],
                "model": raw["model"],
                "label": model_display_name(raw["model"]),
                "source": "override",
            }

        task_type = SCREEN_DEFAULT_TASK.get(screen, "req_analyze")
        tier = _resolve_effective_tier(org)

        if tier in ("free", "low_cost"):
            table = FREE_ROUTING if tier == "free" else LOW_COST_ROUTING
            routing = table.get(task_type, {})
            primary = routing.get(
                "model_1",
                ("openrouter", "openai/gpt-oss-120b:free"),
            )
            provider, model = primary
            return {
                "provider": provider,
                "model": model,
                "label": model_display_name(model),
                "source": tier,
            }

        provider, model = DEFAULT_PAID_ROUTING.get(
            task_type, ("anthropic", "claude-sonnet-4-5")
        )
        return {
            "provider": provider,
            "model": model,
            "label": model_display_name(model),
            "source": "premium",
        }


def _build_anthropic_messages(prompt: str, context: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": prompt})
    return messages


def _build_openai_messages(
    prompt: str,
    context: str,
    system_msg: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": prompt})
    return messages


_ai_router: AiRouter | None = None


def get_ai_router() -> AiRouter:
    """Return singleton AiRouter instance."""
    global _ai_router
    if _ai_router is None:
        _ai_router = AiRouter()
    return _ai_router
