"""AI provider routing tables and model catalog."""

from __future__ import annotations

from typing import TypedDict


class RoutingEntry(TypedDict, total=False):
    task_label: str
    model_1: tuple[str, str]
    model_2: tuple[str, str]
    model_3: tuple[str, str]
    model_4: tuple[str, str]
    quality_note: str
    prompt_enhancement: bool
    quality_stars: int


FREE_ROUTING: dict[str, RoutingEntry] = {
    "req_analyze": {
        "task_label": "Requirement Analysis",
        "model_1": ("openrouter", "meta-llama/llama-4-maverick:free"),
        "model_2": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_3": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": (
            "Maverick chosen: 128K context needed for full PDF analysis. "
            "Best free model for long-document understanding."
        ),
        "prompt_enhancement": True,
        "quality_stars": 4,
    },
    "prd_generate": {
        "task_label": "PRD Generation",
        "model_1": ("openrouter", "meta-llama/llama-4-maverick:free"),
        "model_2": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_3": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": (
            "Maverick: best free structured output for nested JSON with features + stories."
        ),
        "quality_stars": 4,
    },
    "srs_generate": {
        "task_label": "SRS Generation (IEEE 830)",
        "model_1": ("openrouter", "meta-llama/llama-4-maverick:free"),
        "model_2": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_3": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": "Maverick handles IEEE 830 numbered FR format reliably.",
        "quality_stars": 4,
    },
    "req_synthesize": {
        "task_label": "Feedback Synthesis",
        "model_1": ("openrouter", "meta-llama/llama-4-maverick:free"),
        "model_2": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_3": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": "Combining 2 docs needs 128K context.",
        "quality_stars": 4,
    },
    "arch_generate": {
        "task_label": "Architecture Suite",
        "model_1": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_2": ("openrouter", "meta-llama/llama-4-maverick:free"),
        "model_3": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": (
            "Llama 3.3 70B first: most reliable for deeply nested JSON schemas "
            "(db_schema, api_endpoints structure). Maverick as fallback."
        ),
        "quality_stars": 4,
    },
    "prd_rewrite": {
        "task_label": "PRD Rewrite",
        "model_1": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_2": ("openrouter", "meta-llama/llama-4-maverick:free"),
        "model_3": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": "70B reliable for guided rewrite tasks.",
        "quality_stars": 4,
    },
    "srs_rewrite": {
        "task_label": "SRS Rewrite",
        "model_1": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_2": ("openrouter", "meta-llama/llama-4-maverick:free"),
        "model_3": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": "70B handles structured SRS rewrites.",
        "quality_stars": 4,
    },
    "spec_generate": {
        "task_label": "Task Specification",
        "model_1": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_2": ("openrouter", "meta-llama/llama-4-maverick:free"),
        "model_3": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": "Specs need precise file paths + code context. 70B most reliable.",
        "quality_stars": 4,
    },
    "arch_single_doc": {
        "task_label": "Architecture Doc (single retry)",
        "model_1": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_2": ("openrouter", "meta-llama/llama-4-maverick:free"),
        "model_3": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": "Single doc retry — 70B sufficient.",
        "quality_stars": 4,
    },
    "module_extract": {
        "task_label": "Module Extraction",
        "model_1": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_2": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_3": ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": "Scout fast + capable for list extraction.",
        "quality_stars": 3,
    },
    "quality_check": {
        "task_label": "Quality Check",
        "model_1": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_2": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_3": ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": "Scout handles yes/no checklist well.",
        "quality_stars": 3,
    },
    "cost_estimate": {
        "task_label": "Cost Estimation",
        "model_1": ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
        "model_2": ("openrouter", "meta-llama/llama-4-scout:free"),
        "model_3": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        "model_4": ("openrouter", "openrouter/auto"),
        "quality_note": (
            "PERT math only — 8B more than enough. "
            "Saves free tier rate limits for complex tasks."
        ),
        "quality_stars": 3,
    },
}

FREE_MODE_QUALITY_BOOSTS: dict[str, str] = {
    "prd_generate": """
        IMPORTANT: Format your response as valid JSON only.
        Be thorough and professional — this is a client document.
        Include at least 5 features with full acceptance criteria.
        Write in business language, not technical jargon.
    """,
    "srs_generate": """
        IMPORTANT: Follow IEEE 830 standard exactly.
        Number all functional requirements as FR-001, FR-002...
        Each FR must have: title, description, input, processing,
        output, error handling, and test criteria.
        Be precise and measurable in NFR thresholds.
    """,
    "arch_generate": """
        IMPORTANT: Return valid JSON only, no markdown.
        Include complete Mermaid diagram strings.
        All file paths must follow the project folder structure.
        Every API endpoint must link to an SRS FR number.
        Every DB column must have correct PostgreSQL types.
    """,
    "spec_generate": """
        IMPORTANT: This spec will be used directly in Cursor IDE.
        Include EXACT file paths from the folder structure.
        Include EXACT column names from the DB schema.
        Include EXACT endpoint paths from the API spec.
        Be specific — vague instructions produce bad code.
    """,
}

DEFAULT_PAID_ROUTING: dict[str, tuple[str, str]] = {
    "req_analyze": ("anthropic", "claude-sonnet-4-5"),
    "req_synthesize": ("anthropic", "claude-sonnet-4-5"),
    "prd_generate": ("anthropic", "claude-sonnet-4-5"),
    "prd_rewrite": ("anthropic", "claude-sonnet-4-5"),
    "srs_generate": ("anthropic", "claude-sonnet-4-5"),
    "srs_rewrite": ("anthropic", "claude-sonnet-4-5"),
    "arch_generate": ("anthropic", "claude-sonnet-4-5"),
    "arch_single_doc": ("anthropic", "claude-sonnet-4-5"),
    "spec_generate": ("anthropic", "claude-sonnet-4-5"),
    "module_extract": ("anthropic", "claude-haiku-4-5"),
    "quality_check": ("anthropic", "claude-haiku-4-5"),
    "cost_estimate": ("anthropic", "claude-haiku-4-5"),
}

SCREEN_DEFAULT_TASK: dict[str, str] = {
    "requirements": "req_analyze",
    "prds": "prd_generate",
    "srs": "srs_generate",
    "architecture": "arch_single_doc",
    "tasks": "spec_generate",
}

MODEL_DISPLAY_NAMES: dict[str, str] = {
    "claude-sonnet-4-5": "Claude Sonnet 4.5",
    "claude-haiku-4-5": "Claude Haiku 4.5",
    "gpt-4o": "GPT-4o",
    "meta-llama/llama-4-maverick:free": "Llama 4 Maverick (free)",
    "meta-llama/llama-3.3-70b-instruct:free": "Llama 3.3 70B (free)",
    "meta-llama/llama-4-scout:free": "Llama 4 Scout (free)",
    "meta-llama/llama-3.1-8b-instruct:free": "Llama 3.1 8B (free)",
    "openrouter/auto": "OpenRouter Auto",
}

PAID_MODEL_OPTIONS: list[dict[str, str]] = [
    {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "label": "Claude Sonnet 4.5",
        "tier": "Best quality",
        "cost": "$$$",
    },
    {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "label": "Claude Haiku 4.5",
        "tier": "Fast",
        "cost": "$",
    },
    {
        "provider": "openai",
        "model": "gpt-4o",
        "label": "GPT-4o",
        "tier": "Versatile",
        "cost": "$$",
    },
]

FREE_MODEL_OPTIONS: list[dict[str, str]] = [
    {
        "provider": "openrouter",
        "model": "meta-llama/llama-4-maverick:free",
        "label": "Llama 4 Maverick (free)",
        "tier": "Best free",
        "cost": "Free",
    },
    {
        "provider": "openrouter",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "label": "Llama 3.3 70B (free)",
        "tier": "Structured JSON",
        "cost": "Free",
    },
    {
        "provider": "openrouter",
        "model": "meta-llama/llama-4-scout:free",
        "label": "Llama 4 Scout (free)",
        "tier": "Fast",
        "cost": "Free",
    },
]


def model_display_name(model: str) -> str:
    """Return a human-readable model label."""
    return MODEL_DISPLAY_NAMES.get(model, model.split("/")[-1])


def free_fallback_chain(task_type: str) -> str:
    """Summarize free-mode fallback chain for UI."""
    routing = FREE_ROUTING.get(task_type)
    if not routing:
        return ""
    labels = []
    for key in ("model_2", "model_3", "model_4"):
        entry = routing.get(key)
        if entry:
            labels.append(model_display_name(entry[1]).replace(" (free)", ""))
    return " → ".join(labels) if labels else ""
