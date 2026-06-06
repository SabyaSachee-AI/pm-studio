import asyncio
import logging

import instructor
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import BaseModel
from typing import TypeVar, Type

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

_MAX_RETRIES = 2


async def ai_call(
    prompt: str,
    response_model: Type[T],
    system: str = "",
    context: str = "",
    max_tokens: int = 4000,
) -> T:
    """
    ALL AI calls go through this function.
    Retries on failure; falls back to OpenAI when configured.
    ALWAYS returns validated Pydantic object.
    """
    settings = get_settings()
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            if settings.anthropic_api_key:
                return await _call_anthropic(
                    settings.anthropic_api_key,
                    prompt,
                    response_model,
                    system,
                    context,
                    max_tokens,
                )
            if settings.openai_api_key:
                return await _call_openai(
                    settings.openai_api_key,
                    prompt,
                    response_model,
                    system,
                    context,
                    max_tokens,
                )
            raise ValueError("ANTHROPIC_API_KEY or OPENAI_API_KEY must be set")
        except Exception as exc:
            last_error = exc
            logger.warning("AI call attempt %s failed: %s", attempt + 1, exc)
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)

    if (
        settings.openai_api_key
        and settings.anthropic_api_key
        and last_error is not None
    ):
        try:
            return await _call_openai(
                settings.openai_api_key,
                prompt,
                response_model,
                system,
                context,
                max_tokens,
            )
        except Exception as fallback_exc:
            raise fallback_exc from last_error

    raise last_error or RuntimeError("AI call failed")


async def _call_anthropic(
    api_key: str,
    prompt: str,
    response_model: Type[T],
    system: str,
    context: str,
    max_tokens: int,
) -> T:
    client = instructor.from_anthropic(AsyncAnthropic(api_key=api_key))
    messages = _build_messages(prompt, context)
    return await client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=max_tokens,
        system=system or "You are a professional software engineering assistant.",
        messages=messages,
        response_model=response_model,
    )


async def _call_openai(
    api_key: str,
    prompt: str,
    response_model: Type[T],
    system: str,
    context: str,
    max_tokens: int,
) -> T:
    client = instructor.from_openai(AsyncOpenAI(api_key=api_key))
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": prompt})
    return await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=max_tokens,
        messages=messages,
        response_model=response_model,
    )


def _build_messages(prompt: str, context: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": prompt})
    return messages
