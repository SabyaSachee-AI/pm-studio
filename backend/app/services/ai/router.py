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
from app.services.ai.job_progress import publish_job_progress
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
# Credit depletion (HTTP 402 / "insufficient credits") is not transient — the
# provider stays broke until the user tops up. Skip it for a long window so the
# fallback chain doesn't waste every run retrying a depleted provider.
_COOLDOWN_CREDIT_DEPLETED_SEC = 6 * 3600
_SAME_MODEL_RATE_LIMIT_RETRIES = 1
_RATE_LIMIT_BACKOFF_BASE_SEC = 1.0
_RATE_LIMIT_BACKOFF_MAX_SEC = 30.0
_CONTINUE_INSTRUCTION = (
    "Continue exactly where the assistant left off. "
    "Do not repeat previous sentences or add introductory remarks."
)

_PROVIDER_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "cerebras": "https://api.cerebras.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "sambanova": "https://api.sambanova.ai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "huggingface": "https://router.huggingface.co/v1",
    "aimlapi": "https://api.aimlapi.com/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "alibaba": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "github": "https://models.inference.ai.azure.com",
}

_OPENAI_COMPAT_INSTRUCTOR_MODES: dict[str, instructor.Mode] = {
    "openai": instructor.Mode.JSON,
    "openrouter": instructor.Mode.JSON,
    "groq": instructor.Mode.TOOLS,
    "together": instructor.Mode.JSON,
    "gemini": instructor.Mode.JSON,
    "cerebras": instructor.Mode.JSON,
    "deepseek": instructor.Mode.JSON,
    "sambanova": instructor.Mode.JSON,
    "nvidia": instructor.Mode.JSON,
    "huggingface": instructor.Mode.JSON,
    "aimlapi": instructor.Mode.JSON,
    "siliconflow": instructor.Mode.JSON,
    "alibaba": instructor.Mode.JSON,
    "github": instructor.Mode.JSON,
}

_PROVIDER_OUTPUT_CAPS: dict[str, int] = {
    "groq": 8192,
    "cerebras": 8192,
    "deepseek": 8192,
    "sambanova": 8192,
    "nvidia": 4096,
    "huggingface": 8192,
    "aimlapi": 8192,
    "siliconflow": 8192,
    "alibaba": 8192,
    "github": 4096,
}


def _effective_max_tokens(provider: str, requested: int, task_type: str) -> int:
    """Clamp max_tokens per provider limits. Arch tasks get higher ceilings on capable providers."""
    cap = _PROVIDER_OUTPUT_CAPS.get(provider, requested)
    if task_type.startswith("arch_") or task_type in ("code_generate", "code_polish"):
        # Large-context providers can handle full arch doc / code output without truncation.
        if provider == "gemini":
            cap = max(cap, 24000)
        elif provider in ("anthropic", "openai", "openrouter", "deepseek", "together",
                          "siliconflow", "alibaba", "aimlapi", "huggingface"):
            cap = max(cap, 16000)
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


def _is_credit_depleted_error(exc: BaseException) -> bool:
    """HTTP 402 or 'insufficient credits' — provider is out of money, not rate limited."""
    if getattr(exc, "status_code", None) == 402:
        return True
    msg = str(exc).lower()
    return (
        "402" in msg
        or "depleted" in msg
        or "insufficient credit" in msg
        or "insufficient_quota" in msg
        or "payment required" in msg
        or "out of credit" in msg
        or ("billing" in msg and "credit" in msg)
    )


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
    if task_type.startswith("arch_") or task_type in ("code_generate", "code_polish"):
        return float(_ARCH_TASK_TIMEOUT_SEC)
    return float(_DEFAULT_TASK_TIMEOUT_SEC)


def _rate_limit_backoff_sec(retry_index: int) -> float:
    """Exponential backoff capped at 30s (1s, 2s, 4s, …)."""
    return min(
        _RATE_LIMIT_BACKOFF_BASE_SEC * (2 ** max(retry_index - 1, 0)),
        _RATE_LIMIT_BACKOFF_MAX_SEC,
    )


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
        assistant_prefill: str = "",
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
                assistant_prefill=assistant_prefill,
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
                assistant_prefill=assistant_prefill,
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
            assistant_prefill=assistant_prefill,
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
            "sambanova": settings.sambanova_api_key,
            "nvidia": settings.nvidia_api_key,
            "huggingface": settings.huggingface_api_key,
            "aimlapi": settings.aimlapi_api_key,
            "siliconflow": settings.siliconflow_api_key,
            "alibaba": settings.alibaba_api_key,
            "github": settings.github_api_key,
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
        assistant_prefill: str = "",
    ) -> T:
        models_in_chain: list[tuple[str, str]] = []
        # Walk the FULL defined chain (deep fallback): try model_1, model_2, …
        # until there are no more entries — supports 20+ model fallback chains.
        attempt_num = 1
        while True:
            entry = routing.get(f"model_{attempt_num}")
            if not entry:
                break
            models_in_chain.append(entry)
            attempt_num += 1

        if not models_in_chain:
            raise RuntimeError(f"Empty model chain for {task_type}, tier={tier}")

        publish_job_progress(
            phase="starting",
            message="Selecting AI model…",
            attempt=0,
        )

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
                publish_job_progress(
                    phase="rate_limited",
                    message=f"{model_display_name(model)} cooling down — trying next model…",
                    current_model=model_display_name(model),
                    attempt=attempt_num,
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

            publish_job_progress(
                current_model=model_display_name(model),
                current_provider=provider,
                phase="generating",
                message=f"Using {model_display_name(model)}…",
                attempt=attempt_num,
            )

            model_rate_retries = 0
            while model_rate_retries <= _SAME_MODEL_RATE_LIMIT_RETRIES:
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
                        assistant_prefill=assistant_prefill,
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
                    break
                except Exception as exc:
                    if _is_credit_depleted_error(exc):
                        last_error = f"Credits depleted: {provider}/{model}"
                        await _set_cooling(
                            provider,
                            model,
                            _COOLDOWN_CREDIT_DEPLETED_SEC,
                            "provider",
                        )
                        logger.warning(
                            "Credits depleted on %s/%s — skipping provider for %dh",
                            provider,
                            model,
                            _COOLDOWN_CREDIT_DEPLETED_SEC // 3600,
                            extra={"tier": tier},
                        )
                        publish_job_progress(
                            phase="rate_limited",
                            message=(
                                f"{model_display_name(model)} out of credits — "
                                "switching provider…"
                            ),
                            current_model=model_display_name(model),
                            attempt=attempt_num,
                        )
                        break
                    is_rate_limit = _is_rate_limit_error(exc)
                    last_error = (
                        f"Rate limit: {provider}/{model}"
                        if is_rate_limit
                        else str(exc)[:200]
                    )
                    if is_rate_limit:
                        if model_rate_retries < _SAME_MODEL_RATE_LIMIT_RETRIES:
                            backoff = _rate_limit_backoff_sec(model_rate_retries + 1)
                            logger.warning(
                                "Rate limited on %s/%s — retrying same model in %.1fs",
                                provider,
                                model,
                                backoff,
                                extra={"tier": tier},
                            )
                            await asyncio.sleep(backoff)
                            model_rate_retries += 1
                            continue
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
                        publish_job_progress(
                            phase="rate_limited",
                            message=f"Rate limit on {model_display_name(model)} — switching model…",
                            current_model=model_display_name(model),
                            attempt=attempt_num,
                        )
                        await asyncio.sleep(_rate_limit_backoff_sec(attempt_num))
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
                    break

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
        assistant_prefill: str = "",
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
            assistant_prefill=assistant_prefill,
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
        assistant_prefill: str = "",
    ) -> T:
        system_msg = system or "You are a professional software engineering assistant."
        messages = _build_openai_messages(
            prompt, context, system_msg, assistant_prefill=assistant_prefill
        )

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
                messages=_build_anthropic_messages(
                    prompt, context, assistant_prefill=assistant_prefill
                ),
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


def _build_anthropic_messages(
    prompt: str,
    context: str,
    assistant_prefill: str = "",
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": prompt})
    if assistant_prefill.strip():
        messages.append({"role": "assistant", "content": assistant_prefill.strip()})
        messages.append({"role": "user", "content": _CONTINUE_INSTRUCTION})
    return messages


def _build_openai_messages(
    prompt: str,
    context: str,
    system_msg: str,
    assistant_prefill: str = "",
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": prompt})
    if assistant_prefill.strip():
        messages.append({"role": "assistant", "content": assistant_prefill.strip()})
        messages.append({"role": "user", "content": _CONTINUE_INSTRUCTION})
    return messages


_ai_router: AiRouter | None = None


def get_ai_router() -> AiRouter:
    """Return singleton AiRouter instance."""
    global _ai_router
    if _ai_router is None:
        _ai_router = AiRouter()
    return _ai_router
