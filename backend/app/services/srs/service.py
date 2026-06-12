"""SRS generation business logic."""

from app.schemas.srs import SRSSchema
from app.services.ai.chunker import chunked_srs


async def generate_srs_ai(
    prd_content: dict,
    project_name: str,
) -> SRSSchema:
    """Generate IEEE 830 SRS from PRD content.

    Uses chunked_srs to split features into batches so every model
    in the fallback chain (including 8K-context free models) can
    contribute.  FRs are renumbered sequentially after merge.
    """
    return await chunked_srs(
        prd_content=prd_content,
        project_name=project_name,
    )
