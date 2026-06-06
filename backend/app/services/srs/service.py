"""SRS generation business logic."""

from app.schemas.srs import SRSSchema
from app.services.ai.base import ai_call


async def generate_srs_ai(
    prd_content: dict,
    project_name: str,
) -> SRSSchema:
    """Generate IEEE 830 SRS from approved PRD content."""
    features = "\n".join(
        [
            f"- [{f['priority'].upper()}] {f['title']}: {f['description']}"
            for f in prd_content.get("features", [])
        ]
    )

    user_stories = "\n".join(
        [
            f"- As a {s['as_a']}, I want to {s['i_want_to']}, so that {s['so_that']}"
            for s in prd_content.get("user_stories", [])
        ]
    )

    prompt = f"""
You are a senior software architect writing an IEEE 830 Software Requirements Specification.

Project: {project_name}

PRD Summary:
{prd_content.get("executive_summary", "")}

Features to implement:
{features}

User Stories:
{user_stories}

Out of Scope:
{chr(10).join(f"- {item}" for item in prd_content.get("out_of_scope", []))}

Generate a complete SRS with:
- Introduction and scope
- Glossary/definitions
- Numbered functional requirements (FR-001, FR-002...)
  Each FR must have: fr_number, title, description, priority, test_criteria
- Non-functional requirements by category (Performance, Security, Usability, Reliability, Scalability)
  Each NFR must have: category, description, metric, threshold
- System constraints
- Assumptions and dependencies

Generate exactly 12 functional requirements and 6 non-functional requirements.
Keep each description under 100 words. Keep test_criteria to 2 items max per FR.
"""

    system = """You are an expert software architect writing IEEE 830 compliant SRS documents.
Be specific, measurable, and testable.
Return strictly structured JSON matching the schema exactly."""

    result = await ai_call(
        prompt=prompt,
        response_model=SRSSchema,
        system=system,
        max_tokens=16000,
    )
    return result
