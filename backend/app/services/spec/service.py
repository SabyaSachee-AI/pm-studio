"""Technical task specification AI generation."""

from app.schemas.spec import TaskSpecSchema
from app.services.ai.base import ai_call


async def generate_spec_ai(
    task_title: str,
    task_description: str,
    module_name: str,
    fr_references: list,
    srs_content: dict,
    project_name: str,
) -> TaskSpecSchema:
    """Generate a developer-ready technical spec from task and SRS context."""
    relevant_frs = []
    if srs_content and fr_references:
        all_frs = srs_content.get("functional_requirements", [])
        relevant_frs = [
            fr for fr in all_frs if fr.get("fr_number") in fr_references
        ]

    frs_text = (
        "\n".join(
            [
                f"{fr['fr_number']}: {fr['title']}\n  {fr['description']}"
                for fr in relevant_frs
            ]
        )
        if relevant_frs
        else "No specific FRs linked"
    )

    prompt = f"""
You are a senior software architect writing a technical specification for a developer.

Project: {project_name}
Module: {module_name or "General"}
Task: {task_title}
Description: {task_description or "No description provided"}

Linked Functional Requirements:
{frs_text}

Generate a complete Technical Task Specification that a developer can use directly in Cursor AI.
Be specific about file paths, function names, and implementation details.
The spec must be immediately actionable — no vague instructions.

Keep each list to maximum 5 items. Keep descriptions under 80 words each.
Be specific and actionable but concise.
"""

    system = """You are an expert software architect writing precise technical specifications.
Be specific, actionable, and implementation-ready.
A junior developer should be able to implement this task from your spec alone.
Return strictly structured JSON."""

    result = await ai_call(
        prompt=prompt,
        response_model=TaskSpecSchema,
        system=system,
        max_tokens=16000,
    )
    return result
