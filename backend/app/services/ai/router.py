"""AI routing: free mode chains, paid defaults, and per-screen overrides."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Type, TypeVar
from uuid import UUID

import instructor
from anthropic import APIStatusError, AsyncAnthropic, RateLimitError as AnthropicRateLimitError
from openai import AsyncOpenAI, RateLimitError as OpenAIRateLimitError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SyncSessionLocal
from app.models.organization import Organization
from app.services.ai.providers import (
    DEFAULT_PAID_ROUTING,
    FREE_MODE_QUALITY_BOOSTS,
    FREE_ROUTING,
    SCREEN_DEFAULT_TASK,
    model_display_name,
)

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

_RATE_LIMIT_ERRORS = (AnthropicRateLimitError, OpenAIRateLimitError)


class AiRouter:
    """Route AI calls through free chains, paid defaults, or screen overrides."""

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

        override = screen_override
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
                free_mode=org.free_mode_enabled,
            )

        if org.free_mode_enabled:
            routing = FREE_ROUTING.get(task_type)
            if not routing:
                raise ValueError(f"No free routing defined for task: {task_type}")
            enhanced_prompt = prompt
            if task_type in FREE_MODE_QUALITY_BOOSTS:
                enhanced_prompt = f"{FREE_MODE_QUALITY_BOOSTS[task_type].strip()}\n\n{prompt}"
            return await self._try_free_chain(
                routing,
                enhanced_prompt,
                response_model,
                system,
                context,
                max_tokens,
                task_type,
                org,
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
            free_mode=False,
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
        if provider == "anthropic" and settings.anthropic_api_key:
            return settings.anthropic_api_key
        if provider == "openai" and settings.openai_api_key:
            return settings.openai_api_key
        if provider == "openrouter" and settings.openrouter_api_key:
            return settings.openrouter_api_key
        return None

    def _provider_enabled(self, provider: str, org: Organization) -> bool:
        configs = org.ai_provider_configs or {}
        provider_cfg = configs.get(provider) or {}
        if provider_cfg.get("is_enabled") is False:
            return False
        return self._get_api_key(provider, org) is not None

    async def _try_free_chain(
        self,
        routing: dict[str, Any],
        prompt: str,
        response_model: Type[T],
        system: str,
        context: str,
        max_tokens: int,
        task_type: str,
        org: Organization,
    ) -> T:
        if not self._provider_enabled("openrouter", org):
            raise RuntimeError(
                "OpenRouter not configured. Add OpenRouter API key to use free mode."
            )

        last_error: str | None = None
        for attempt_num in range(1, 5):
            entry = routing.get(f"model_{attempt_num}")
            if not entry:
                continue
            _provider, model = entry
            try:
                result = await self._call_provider(
                    provider="openrouter",
                    model=model,
                    api_key=self._get_api_key("openrouter", org) or "",
                    prompt=prompt,
                    response_model=response_model,
                    system=system,
                    context=context,
                    max_tokens=max_tokens,
                )
                await self._log_usage(
                    task_type=task_type,
                    provider="openrouter",
                    model=model,
                    org_id=org.id,
                    free_mode=True,
                    attempt_number=attempt_num,
                )
                return result
            except _RATE_LIMIT_ERRORS:
                last_error = f"Rate limit: {model}"
                await asyncio.sleep(5)
                continue
            except Exception as exc:
                last_error = str(exc)[:200]
                logger.exception(
                    "Free model failed, trying next",
                    extra={"model": model, "attempt": attempt_num},
                )
                continue

        raise RuntimeError(
            f"All free models failed for {task_type}. "
            f"Last error: {last_error}. "
            "Please try again or switch to paid providers."
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
        free_mode: bool,
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

        result = await self._call_provider(
            provider=provider,
            model=model,
            api_key=api_key or "",
            prompt=prompt,
            response_model=response_model,
            system=system,
            context=context,
            max_tokens=max_tokens,
        )
        await self._log_usage(
            task_type=task_type,
            provider=provider,
            model=model,
            org_id=org.id,
            free_mode=free_mode,
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
    ) -> T:
        system_msg = system or "You are a professional software engineering assistant."
        if provider == "anthropic":
            client = instructor.from_anthropic(AsyncAnthropic(api_key=api_key))
            return await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_msg,
                messages=_build_messages(prompt, context),
                response_model=response_model,
            )
        if provider in ("openai", "openrouter"):
            base_url = (
                "https://openrouter.ai/api/v1" if provider == "openrouter" else None
            )
            default_headers = (
                {"HTTP-Referer": "https://pmstudio.app", "X-Title": "PM Studio"}
                if provider == "openrouter"
                else None
            )
            client = instructor.from_openai(
                AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    default_headers=default_headers,
                )
            )
            messages: list[dict[str, str]] = []
            if system:
                messages.append({"role": "system", "content": system_msg})
            if context:
                messages.append({"role": "user", "content": f"Context:\n{context}"})
                messages.append({"role": "assistant", "content": "Understood."})
            messages.append({"role": "user", "content": prompt})
            return await client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                response_model=response_model,
            )
        raise ValueError(f"Unsupported provider: {provider}")

    async def _log_usage(
        self,
        task_type: str,
        provider: str,
        model: str,
        org_id: UUID,
        free_mode: bool,
        attempt_number: int,
    ) -> None:
        logger.info(
            "AI usage",
            extra={
                "task_type": task_type,
                "provider": provider,
                "model": model,
                "org_id": str(org_id),
                "free_mode": free_mode,
                "attempt": attempt_number,
            },
        )

    def resolve_screen_model(
        self,
        org: Organization,
        screen: str,
    ) -> dict[str, str]:
        """Return effective provider/model label for a screen."""
        overrides = org.screen_model_overrides or {}
        raw = overrides.get(screen)
        if raw and isinstance(raw, dict) and raw.get("provider") and raw.get("model"):
            provider = raw["provider"]
            model = raw["model"]
            return {
                "provider": provider,
                "model": model,
                "label": model_display_name(model),
                "source": "override",
            }

        task_type = SCREEN_DEFAULT_TASK.get(screen, "req_analyze")
        if org.free_mode_enabled:
            routing = FREE_ROUTING.get(task_type, {})
            primary = routing.get("model_1", ("openrouter", "meta-llama/llama-4-maverick:free"))
            provider, model = primary
            return {
                "provider": provider,
                "model": model,
                "label": model_display_name(model),
                "source": "free_mode",
            }

        provider, model = DEFAULT_PAID_ROUTING.get(
            task_type, ("anthropic", "claude-sonnet-4-5")
        )
        return {
            "provider": provider,
            "model": model,
            "label": model_display_name(model),
            "source": "paid_default",
        }


def _build_messages(prompt: str, context: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
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
