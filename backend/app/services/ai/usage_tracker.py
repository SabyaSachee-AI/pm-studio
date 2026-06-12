"""Redis-backed daily AI usage tracking — requests and estimated tokens per provider."""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

# Published free-tier daily limits per provider (June 2026)
PROVIDER_DAILY_LIMITS: dict[str, dict[str, int | str]] = {
    "openrouter": {
        "requests_per_day": 1000,        # with $10 credits; 50 without
        "requests_per_day_no_credits": 50,
        "tokens_per_day": 0,             # no token cap — request-based only
        "rpm": 20,
        "label": "OpenRouter",
        "tier": "free",
        "color": "purple",
    },
    "groq": {
        "requests_per_day": 1000,        # per model (tracks aggregate here)
        "tokens_per_day": 0,             # tracked as TPM cap, not TPD
        "tpm": 6000,                     # 30K for Llama 4 Scout
        "rpm": 30,
        "label": "Groq ⚡",
        "tier": "free",
        "color": "orange",
    },
    "gemini": {
        "requests_per_day": 1500,
        "tokens_per_day": 0,
        "tpm": 250000,
        "rpm": 10,
        "label": "Google Gemini",
        "tier": "free",
        "color": "blue",
    },
    "cerebras": {
        "requests_per_day": 0,           # token-limited, not request-limited
        "tokens_per_day": 1_000_000,
        "tpm": 60000,
        "rpm": 30,
        "label": "Cerebras",
        "tier": "free",
        "color": "cyan",
    },
    "together": {
        "requests_per_day": 0,           # no published hard limit
        "tokens_per_day": 0,
        "rpm": 0,
        "label": "Together AI 🤝",
        "tier": "free",
        "color": "blue",
    },
    "anthropic": {
        "requests_per_day": 0,           # paid — no hard daily limit
        "tokens_per_day": 0,
        "label": "Anthropic",
        "tier": "paid",
        "color": "pink",
    },
    "openai": {
        "requests_per_day": 0,
        "tokens_per_day": 0,
        "label": "OpenAI",
        "tier": "paid",
        "color": "green",
    },
    "deepseek": {
        "requests_per_day": 0,
        "tokens_per_day": 0,
        "label": "DeepSeek",
        "tier": "paid",
        "color": "indigo",
    },
}


def _today_key(org_id: str, provider: str) -> str:
    today = date.today().isoformat()
    return f"ai_usage:{org_id}:{provider}:{today}"


async def increment_usage(
    org_id: str,
    provider: str,
    requests: int = 1,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    """Increment daily usage counters for a provider. Fire-and-forget — never raises."""
    try:
        import redis.asyncio as redis  # type: ignore[import]

        from app.core.config import get_settings

        settings = get_settings()
        key = _today_key(str(org_id), provider)
        r = redis.from_url(settings.redis_url, decode_responses=True)
        async with r:
            pipe = r.pipeline()
            pipe.hincrby(key, "requests", requests)
            if tokens_in:
                pipe.hincrby(key, "tokens_in", tokens_in)
            if tokens_out:
                pipe.hincrby(key, "tokens_out", tokens_out)
            pipe.expire(key, 172_800)  # 48-hour TTL
            await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.debug("AI usage tracking failed (non-fatal): %s", exc)


async def get_daily_usage(org_id: str) -> dict[str, dict[str, int]]:
    """Return today's usage per provider for a given org. Returns {} on error."""
    try:
        import redis.asyncio as redis  # type: ignore[import]

        from app.core.config import get_settings

        settings = get_settings()
        providers = list(PROVIDER_DAILY_LIMITS.keys())
        r = redis.from_url(settings.redis_url, decode_responses=True)
        result: dict[str, dict[str, int]] = {}
        async with r:
            for provider in providers:
                key = _today_key(str(org_id), provider)
                data = await r.hgetall(key)
                if data:
                    result[provider] = {
                        "requests": int(data.get("requests", 0)),
                        "tokens_in": int(data.get("tokens_in", 0)),
                        "tokens_out": int(data.get("tokens_out", 0)),
                    }
                else:
                    result[provider] = {"requests": 0, "tokens_in": 0, "tokens_out": 0}
        return result
    except Exception as exc:  # noqa: BLE001
        logger.debug("AI usage fetch failed: %s", exc)
        return {p: {"requests": 0, "tokens_in": 0, "tokens_out": 0} for p in PROVIDER_DAILY_LIMITS}
