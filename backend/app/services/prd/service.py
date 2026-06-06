"""PRD generation business logic."""

from app.schemas.prd import PRDSchema
from app.services.ai.base import ai_call


async def generate_prd_ai(
    requirement_text: str,
    analysis_result: dict,
    project_name: str,
) -> PRDSchema:
    """Generate a full PRD from requirement text and analysis."""
    gaps_summary = "\n".join(
        [
            f"- [{g['category'].upper()}] {g['description']}"
            for g in analysis_result.get("gaps", [])
        ]
    )

    prompt = f"""
You are a senior product manager. Generate a comprehensive Product Requirements Document (PRD).

Project: {project_name}
Project Type: {analysis_result.get("project_type", "Software")}

Original Requirements:
{requirement_text[:5000]}

Known Gaps Identified:
{gaps_summary}

Business Risks:
{chr(10).join(f"- {r}" for r in analysis_result.get("business_risks", []))}

Generate a complete, professional PRD with:
- Clear executive summary
- Problem statement
- Target user personas
- Prioritized feature list (must-have, should-have, nice-to-have)
- User stories with acceptance criteria
- What is explicitly out of scope
- Success metrics
- Assumptions made
"""

    system = """You are an expert product manager creating professional PRDs.
Be specific, actionable, and comprehensive.
Return strictly structured JSON matching the schema exactly."""

    result = await ai_call(
        prompt=prompt,
        response_model=PRDSchema,
        system=system,
        max_tokens=8000,
    )
    return result
