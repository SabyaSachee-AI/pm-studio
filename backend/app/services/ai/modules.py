"""AI module + task extraction from approved PRD and SRS."""

from app.schemas.module import ModuleListSchema
from app.services.ai.base import ai_call


async def generate_modules_ai(
    project_name: str,
    prd_content: dict,
    srs_content: dict,
) -> ModuleListSchema:
    """Extract modules and implementation tasks from PRD + SRS context."""
    features = prd_content.get("features", [])
    features_text = "\n".join(
        f"- {f.get('title', '')}: {f.get('description', '')} [{f.get('priority', '')}]"
        for f in features[:12]
    )
    frs = srs_content.get("functional_requirements", [])
    frs_text = "\n".join(
        f"{fr.get('fr_number', '')}: {fr.get('title', '')} — {fr.get('description', '')}"
        for fr in frs[:15]
    )

    prompt = f"""
You are a senior technical project manager breaking a software project into modules and tasks.

Project: {project_name}

PRD Features:
{features_text or "No features listed"}

SRS Functional Requirements:
{frs_text or "No FRs listed"}

Extract logical software modules (e.g. Authentication, Payments, Catalog) and for each module
list concrete implementation tasks a developer can pick up on a Kanban board.

Keep each module to maximum 5 tasks. Link tasks to FR numbers where applicable (fr_references).
Priorities: critical, high, medium, low.
Be specific and actionable but concise.
"""

    system = """You are an expert software project planner.
Return strictly structured JSON matching the schema.
Each task must be independently implementable."""

    return await ai_call(
        prompt=prompt,
        response_model=ModuleListSchema,
        system=system,
        max_tokens=12000,
    )
