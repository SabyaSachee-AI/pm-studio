"""PRD generation business logic."""

from app.schemas.prd import PRDSchema
from app.services.ai.chunker import chunked_prd


async def generate_prd_ai(
    requirement_text: str,
    analysis_result: dict,
    project_name: str,
) -> PRDSchema:
    """Generate a full PRD — no truncation of requirement text.

    Uses chunked_prd so the full document is processed even with
    8K-context free models.  The analysis_result is passed to every
    chunk so the model always has full project context.
    """
    return await chunked_prd(
        requirement_text=requirement_text,
        analysis_result=analysis_result,
        project_name=project_name,
    )
