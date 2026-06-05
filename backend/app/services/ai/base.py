import os
import instructor
from anthropic import AsyncAnthropic
from pydantic import BaseModel
from typing import TypeVar, Type

T = TypeVar("T", bound=BaseModel)


async def ai_call(
    prompt: str,
    response_model: Type[T],
    system: str = "",
    context: str = "",
    max_tokens: int = 4000,
) -> T:
    """
    ALL AI calls go through this function.
    Client is created lazily to ensure API key is loaded from env.
    ALWAYS returns validated Pydantic object.
    NEVER returns raw markdown or string.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set in environment")

    client = instructor.from_anthropic(AsyncAnthropic(api_key=api_key))

    messages = []
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": prompt})

    return await client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=max_tokens,
        system=system or "You are a professional software engineering assistant.",
        messages=messages,
        response_model=response_model,
    )
