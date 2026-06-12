"""Central AI call entry point — delegates to AiRouter for provider routing."""

from __future__ import annotations

import logging
from typing import Type, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.router import get_ai_router

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


async def ai_call(
    prompt: str,
    response_model: Type[T],
    system: str = "",
    context: str = "",
    max_tokens: int = 4000,
    task_type: str = "req_analyze",
    screen: str | None = None,
    org_id: UUID | None = None,
    db: AsyncSession | None = None,
    assistant_prefill: str = "",
) -> T:
    """
    ALL AI calls go through this function.
    Routes via AiRouter (free chains, paid defaults, per-screen overrides).
    ALWAYS returns validated Pydantic object.
    """
    return await get_ai_router().call(
        task_type=task_type,
        prompt=prompt,
        response_model=response_model,
        system=system,
        context=context,
        max_tokens=max_tokens,
        screen=screen,
        org_id=org_id,
        db=db,
        assistant_prefill=assistant_prefill,
    )
