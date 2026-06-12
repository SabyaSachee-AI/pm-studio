"""Requirement document extraction and AI analysis."""

import fitz

from app.schemas.requirement import RequirementAnalysisSchema
from app.services.ai.chunker import chunked_analysis


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF using PyMuPDF."""
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


async def analyze_requirements_ai(text: str) -> RequirementAnalysisSchema:
    """Analyse full requirement text — no truncation.

    Uses chunked_analysis so any-size PDF is processed completely,
    even when the active model chain includes 8K-context free models.
    """
    return await chunked_analysis(text)
