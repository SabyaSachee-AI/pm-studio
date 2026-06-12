"""AI module + task extraction from approved PRD, SRS, and optional Architecture."""

from typing import Any

from app.schemas.module import ModuleListSchema
from app.services.ai.chunker import chunked_modules


async def generate_modules_ai(
    project_name: str,
    prd_content: dict,
    srs_content: dict,
    arch_content: dict[str, Any] | None = None,
    target_frs: list[str] | None = None,
) -> ModuleListSchema:
    """Extract modules and implementation tasks from PRD + SRS + Architecture.

    Delegates to chunked_modules so large SRS documents are split into
    FR batches — every model in the fallback chain (including 8K-context
    free models) can contribute without being overloaded.
    """
    return await chunked_modules(
        project_name=project_name,
        prd_content=prd_content,
        srs_content=srs_content,
        arch_content=arch_content,
        target_frs=target_frs,
    )
