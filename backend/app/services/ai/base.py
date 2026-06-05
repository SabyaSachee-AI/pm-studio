import os
import instructor
from anthropic import AsyncAnthropic
from pydantic import BaseModel
from typing import TypeVar, Type

T = TypeVar("T", bound=BaseModel)

_client = instructor.from_anthropic(
    AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
)

async def ai_call(
    prompt: str,
    response_model: Type[T],
    system: str = "",
    context: str = ""
) -> T:
    messages = []
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": prompt})

    return await _client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=4000,
        system=system or "You are a professional software engineering assistant.",
        messages=messages,
        response_model=response_model,
    )