"""Requirement document extraction and AI analysis."""

import fitz

from app.schemas.requirement import RequirementAnalysisSchema
from app.services.ai.base import ai_call


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF using PyMuPDF."""
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


async def analyze_requirements_ai(text: str) -> RequirementAnalysisSchema:
    """Analyze extracted text using Claude via ai_call."""
    truncated_text = text[:10000]
    prompt = f"""
    Analyze the following software project requirements document.
    Identify the project type, gaps, risks, technical questions, and missing non-functional requirements.

    Document Text:
    {truncated_text}
    """

    system = "You are an expert software business analyst. Return strictly structured JSON."

    result = await ai_call(
        prompt=prompt,
        response_model=RequirementAnalysisSchema,
        system=system,
    )
    return result
