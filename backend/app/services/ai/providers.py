"""AI provider routing tables and model catalog."""

from __future__ import annotations

from typing import TypedDict

AiTier = str  # "free" | "low_cost" | "premium"

ALL_PROVIDERS: tuple[str, ...] = (
    "anthropic",
    "openai",
    "openrouter",
    "groq",
    "gemini",
    "cerebras",
    "deepseek",
    "together",
    "sambanova",
    "nvidia",
    "huggingface",
    "aimlapi",
    "siliconflow",
    "alibaba",
    "github",
)


class RoutingEntry(TypedDict, total=False):
    task_label: str
    quality_note: str
    prompt_enhancement: bool
    quality_stars: int
    # model_1 .. model_15 populated by _build_free_routing


# ---------------------------------------------------------------------------
# Fallback tails — multi-provider pools (June 2026, 15 providers)
#
# HEAVY — PRD/SRS/architecture/specs/analysis. Large context only.
# Separate quota pools after OpenRouter block: SiliconFlow, Alibaba, HF,
# GitHub, SambaNova, Groq, NVIDIA NIM.
#
# LIGHT — module extract, quality check, cost estimate. Speed first.
# ---------------------------------------------------------------------------

_MAX_CHAIN_MODELS = 20

HEAVY_FREE_TAIL: list[tuple[str, str]] = [
    ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ("openrouter", "openai/gpt-oss-120b:free"),
    ("openrouter", "google/gemma-4-31b-it:free"),
    ("openrouter", "nex-agi/nex-n2-pro:free"),
    ("openrouter", "moonshotai/kimi-k2.6:free"),
    ("openrouter", "poolside/laguna-xs.2:free"),
    ("openrouter", "nvidia/nemotron-3-nano-30b-a3b:free"),
    ("siliconflow", "Qwen/Qwen3.5-35B-A3B"),
    ("siliconflow", "nex-agi/Nex-N2-Pro"),
    ("alibaba", "qwen-long"),
    ("alibaba", "qwen-plus"),
    ("huggingface", "Qwen/Qwen2.5-Coder-32B-Instruct"),
    ("huggingface", "meta-llama/Llama-3.3-70B-Instruct"),
    ("sambanova", "Meta-Llama-3.3-70B-Instruct"),
    ("groq", "llama-3.3-70b-versatile"),
    # 4096-token output cap providers — last resort for heavy tasks
    ("nvidia", "meta/llama-3.1-405b-instruct"),
    ("github", "Llama-4-Scout-17B-16E"),
    ("github", "DeepSeek-R1"),
]

LIGHT_FREE_TAIL: list[tuple[str, str]] = [
    ("groq", "llama-3.3-70b-versatile"),
    ("groq", "llama-3.1-8b-instant"),
    ("cerebras", "zai-glm-4.7"),
    ("cerebras", "gpt-oss-120b"),
    ("siliconflow", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"),
    ("github", "DeepSeek-R1"),
    ("huggingface", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"),
    ("openrouter", "openai/gpt-oss-20b:free"),
    ("openrouter", "nvidia/nemotron-3-nano-30b-a3b:free"),
    ("openrouter", "google/gemma-4-26b-a4b-it:free"),
    ("sambanova", "Meta-Llama-3.3-70B-Instruct"),
    ("openrouter", "moonshotai/kimi-k2.6:free"),
]

LOW_COST_HEAVY_TAIL: list[tuple[str, str]] = [
    ("aimlapi", "deepseek/deepseek-r1"),
    ("aimlapi", "google/gemini-2.5-flash"),
    ("aimlapi", "nvidia/nemotron-3-ultra"),
    ("alibaba", "qwen-max"),
    ("deepseek", "deepseek-reasoner"),
    ("together", "Qwen/Qwen3-Coder-30B-Instruct"),
    *HEAVY_FREE_TAIL,
]

LOW_COST_LIGHT_TAIL: list[tuple[str, str]] = [
    ("deepseek", "deepseek-chat"),
    ("aimlapi", "deepseek/deepseek-r1"),
    *LIGHT_FREE_TAIL,
]


def _build_free_routing(
    *,
    task_label: str,
    top4: list[tuple[str, str]],
    quality_note: str = "",
    quality_stars: int = 4,
    prompt_enhancement: bool = False,
    tail: list[tuple[str, str]] | None = None,
    max_models: int = _MAX_CHAIN_MODELS,
) -> RoutingEntry:
    """Merge task-specific top-4 with a fallback tail; dedupe; cap at max_models."""
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[str, str]] = []
    for entry in top4 + (tail if tail is not None else HEAVY_FREE_TAIL):
        if entry not in seen:
            seen.add(entry)
            ordered.append(entry)
        if len(ordered) >= max_models:
            break
    result: RoutingEntry = {
        "task_label": task_label,
        "quality_note": quality_note,
        "quality_stars": quality_stars,
        "prompt_enhancement": prompt_enhancement,
    }
    for idx, pair in enumerate(ordered, start=1):
        result[f"model_{idx}"] = pair  # type: ignore[literal-required]
    return result

FREE_ROUTING: dict[str, RoutingEntry] = {
    "req_analyze": _build_free_routing(
        task_label="Requirement Analysis",
        top4=[
            ("gemini", "gemini-2.5-flash"),
            ("openrouter", "openrouter/owl-alpha"),
            ("siliconflow", "Qwen/Qwen3.5-35B-A3B"),
            ("alibaba", "qwen-long"),
        ],
        quality_note=(
            "Gemini 2.5 Flash primary; Owl Alpha 1.05M ctx; SiliconFlow + "
            "Alibaba Qwen Long as separate free quota pools."
        ),
        quality_stars=5,
        prompt_enhancement=True,
    ),
    "req_synthesize": _build_free_routing(
        task_label="Feedback Synthesis",
        top4=[
            ("gemini", "gemini-2.5-flash"),
            ("openrouter", "openrouter/owl-alpha"),
            ("siliconflow", "nex-agi/Nex-N2-Pro"),
            ("openrouter", "nex-agi/nex-n2-pro:free"),
        ],
        quality_note=(
            "1M-context models fit requirement + full feedback in one call; "
            "Nex N2 Pro adds reasoning for conflict resolution."
        ),
        quality_stars=5,
        prompt_enhancement=True,
    ),
    "prd_generate": _build_free_routing(
        task_label="PRD Generation",
        top4=[
            ("openrouter", "openai/gpt-oss-120b:free"),
            ("gemini", "gemini-2.5-flash"),
            ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
            ("openrouter", "nex-agi/nex-n2-pro:free"),
        ],
        quality_note="GPT-OSS 120B: best structured JSON for PRDSchema.",
        quality_stars=5,
        prompt_enhancement=True,
    ),
    "srs_generate": _build_free_routing(
        task_label="SRS Generation (IEEE 830)",
        top4=[
            ("openrouter", "openai/gpt-oss-120b:free"),
            ("gemini", "gemini-2.5-flash"),
            ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
            ("openrouter", "google/gemma-4-31b-it:free"),
        ],
        quality_note="GPT-OSS 120B follows IEEE 830 numbering reliably.",
        quality_stars=5,
        prompt_enhancement=True,
    ),
    "arch_generate": _build_free_routing(
        task_label="Architecture Suite (6 docs)",
        top4=[
            ("gemini", "gemini-2.5-flash"),
            ("openrouter", "poolside/laguna-m.1:free"),
            ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),
            ("openrouter", "openai/gpt-oss-120b:free"),
        ],
        quality_note=(
            "Gemini 2.5 Flash first — fast reasoning for cross-linked arch JSON. "
            "Laguna M.1 for coding-heavy docs; Nemotron Ultra for max quality."
        ),
        quality_stars=5,
        prompt_enhancement=True,
    ),
    "arch_single_doc": _build_free_routing(
        task_label="Architecture Doc (single)",
        top4=[
            ("openrouter", "poolside/laguna-m.1:free"),
            ("gemini", "gemini-2.5-flash"),
            ("openrouter", "openai/gpt-oss-120b:free"),
            ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
        ],
        quality_stars=4,
    ),
    "spec_generate": _build_free_routing(
        task_label="Task Specification",
        top4=[
            ("openrouter", "poolside/laguna-m.1:free"),
            ("huggingface", "Qwen/Qwen2.5-Coder-32B-Instruct"),
            ("openrouter", "openai/gpt-oss-120b:free"),
            ("siliconflow", "Qwen/Qwen3.5-35B-A3B"),
        ],
        quality_note="Laguna M.1 is purpose-built for code/API specs.",
        quality_stars=5,
        prompt_enhancement=True,
    ),
    "prd_rewrite": _build_free_routing(
        task_label="PRD Rewrite",
        top4=[
            ("openrouter", "openai/gpt-oss-120b:free"),
            ("openrouter", "google/gemma-4-31b-it:free"),
            ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
            ("gemini", "gemini-2.5-flash"),
        ],
        quality_stars=4,
    ),
    "srs_rewrite": _build_free_routing(
        task_label="SRS Rewrite",
        top4=[
            ("openrouter", "openai/gpt-oss-120b:free"),
            ("gemini", "gemini-2.5-flash"),
            ("openrouter", "google/gemma-4-31b-it:free"),
            ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
        ],
        quality_stars=4,
    ),
    "module_extract": _build_free_routing(
        task_label="Module Extraction",
        top4=[
            ("openrouter", "openai/gpt-oss-20b:free"),
            ("groq", "llama-3.3-70b-versatile"),
            ("github", "Llama-4-Scout-17B-16E"),
            ("siliconflow", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"),
        ],
        quality_stars=3,
        tail=LIGHT_FREE_TAIL,
    ),
    "quality_check": _build_free_routing(
        task_label="Quality Check",
        top4=[
            ("openrouter", "openai/gpt-oss-20b:free"),
            ("groq", "llama-3.3-70b-versatile"),
            ("cerebras", "zai-glm-4.7"),
            ("openrouter", "google/gemma-4-26b-a4b-it:free"),
        ],
        quality_stars=3,
        tail=LIGHT_FREE_TAIL,
    ),
    "cost_estimate": _build_free_routing(
        task_label="Cost Estimation",
        top4=[
            ("openrouter", "openai/gpt-oss-20b:free"),
            ("groq", "llama-3.3-70b-versatile"),
            ("cerebras", "zai-glm-4.7"),
            ("openrouter", "google/gemma-4-26b-a4b-it:free"),
        ],
        quality_stars=3,
        tail=LIGHT_FREE_TAIL,
    ),
}

LOW_COST_ROUTING: dict[str, RoutingEntry] = {
    "req_analyze": _build_free_routing(
        task_label="Requirement Analysis (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("aimlapi", "deepseek/deepseek-r1"),
            ("alibaba", "qwen-max"),
            ("gemini", "gemini-2.5-flash"),
        ],
        quality_note="DeepSeek + AIML API + Alibaba Qwen Max — best value for analysis.",
        quality_stars=4,
        tail=LOW_COST_HEAVY_TAIL,
    ),
    "req_synthesize": _build_free_routing(
        task_label="Feedback Synthesis (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("aimlapi", "deepseek/deepseek-r1"),
            ("gemini", "gemini-2.5-flash"),
            ("siliconflow", "nex-agi/Nex-N2-Pro"),
        ],
        quality_stars=4,
        tail=LOW_COST_HEAVY_TAIL,
    ),
    "prd_generate": _build_free_routing(
        task_label="PRD Generation (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("aimlapi", "google/gemini-2.5-flash"),
            ("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
            ("openrouter", "openai/gpt-oss-120b:free"),
        ],
        quality_stars=4,
        prompt_enhancement=True,
        tail=LOW_COST_HEAVY_TAIL,
    ),
    "srs_generate": _build_free_routing(
        task_label="SRS Generation (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("aimlapi", "google/gemini-2.5-flash"),
            ("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
            ("openrouter", "openai/gpt-oss-120b:free"),
        ],
        quality_stars=4,
        prompt_enhancement=True,
        tail=LOW_COST_HEAVY_TAIL,
    ),
    "arch_generate": _build_free_routing(
        task_label="Architecture Suite (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("aimlapi", "nvidia/nemotron-3-ultra"),
            ("gemini", "gemini-2.5-flash"),
            ("openrouter", "poolside/laguna-m.1:free"),
        ],
        quality_note="DeepSeek + AIML Nemotron Ultra; free pools as backup.",
        quality_stars=4,
        prompt_enhancement=True,
        tail=LOW_COST_HEAVY_TAIL,
    ),
    "arch_single_doc": _build_free_routing(
        task_label="Architecture Doc single (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("openrouter", "poolside/laguna-m.1:free"),
            ("aimlapi", "google/gemini-2.5-flash"),
            ("gemini", "gemini-2.5-flash"),
        ],
        quality_stars=4,
        tail=LOW_COST_HEAVY_TAIL,
    ),
    "spec_generate": _build_free_routing(
        task_label="Task Specification (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("together", "Qwen/Qwen3-Coder-30B-Instruct"),
            ("openrouter", "poolside/laguna-m.1:free"),
            ("huggingface", "Qwen/Qwen2.5-Coder-32B-Instruct"),
        ],
        quality_stars=4,
        prompt_enhancement=True,
        tail=LOW_COST_HEAVY_TAIL,
    ),
    "prd_rewrite": _build_free_routing(
        task_label="PRD Rewrite (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("aimlapi", "deepseek/deepseek-r1"),
            ("openrouter", "openai/gpt-oss-120b:free"),
            ("gemini", "gemini-2.5-flash"),
        ],
        quality_stars=4,
        tail=LOW_COST_HEAVY_TAIL,
    ),
    "srs_rewrite": _build_free_routing(
        task_label="SRS Rewrite (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("aimlapi", "deepseek/deepseek-r1"),
            ("openrouter", "openai/gpt-oss-120b:free"),
            ("gemini", "gemini-2.5-flash"),
        ],
        quality_stars=4,
        tail=LOW_COST_HEAVY_TAIL,
    ),
    "module_extract": _build_free_routing(
        task_label="Module Extraction (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("aimlapi", "deepseek/deepseek-r1"),
            ("groq", "llama-3.3-70b-versatile"),
            ("github", "Llama-4-Scout-17B-16E"),
        ],
        quality_stars=3,
        tail=LOW_COST_LIGHT_TAIL,
    ),
    "quality_check": _build_free_routing(
        task_label="Quality Check (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("groq", "llama-3.3-70b-versatile"),
            ("siliconflow", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"),
            ("cerebras", "zai-glm-4.7"),
        ],
        quality_stars=3,
        tail=LOW_COST_LIGHT_TAIL,
    ),
    "cost_estimate": _build_free_routing(
        task_label="Cost Estimation (low cost)",
        top4=[
            ("deepseek", "deepseek-chat"),
            ("groq", "llama-3.3-70b-versatile"),
            ("siliconflow", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"),
            ("cerebras", "zai-glm-4.7"),
        ],
        quality_stars=3,
        tail=LOW_COST_LIGHT_TAIL,
    ),
}

# Default model per tier — used when a task type has no specific routing.
TIER_DEFAULT_MODEL: dict[str, tuple[str, str]] = {
    "free": ("gemini", "gemini-2.5-flash"),          # 1,500 req/day — highest free quota
    "low_cost": ("deepseek", "deepseek-chat"),       # ~$0.14/1M tokens — best value
    "premium": ("anthropic", "claude-sonnet-4-5"),   # best quality
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

TIER_ROUTING_TABLES: dict[str, dict[str, RoutingEntry]] = {
    "free": FREE_ROUTING,
    "low_cost": LOW_COST_ROUTING,
    "premium": {},  # uses DEFAULT_PAID_ROUTING directly
}

MODEL_DISPLAY_NAMES: dict[str, str] = {
    "claude-sonnet-4-5": "Claude Sonnet 4.5",
    "claude-haiku-4-5": "Claude Haiku 4.5",
    "gpt-4o": "GPT-4o",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "deepseek-chat": "DeepSeek V3",
    "openai/gpt-oss-120b:free": "OpenAI GPT-OSS 120B (FREE)",
    "openai/gpt-oss-20b:free": "OpenAI GPT-OSS 20B (FREE)",
    "nvidia/nemotron-3-super-120b-a12b:free": "NVIDIA Nemotron 3 Super (FREE)",
    "nvidia/nemotron-3-ultra-550b-a55b:free": "NVIDIA Nemotron Ultra 550B (FREE)",
    "google/gemma-4-31b-it:free": "Google Gemma 4 31B (FREE)",
    "google/gemma-4-26b-a4b-it:free": "Google Gemma 4 26B MoE (FREE)",
    "poolside/laguna-m.1:free": "Poolside Laguna M.1 (FREE)",
    "poolside/laguna-xs.2:free": "Poolside Laguna XS.2 (FREE)",
    "openrouter/owl-alpha": "OpenRouter Owl Alpha (FREE)",
    "moonshotai/kimi-k2.6:free": "Kimi K2.6 (FREE)",
    "nex-agi/nex-n2-pro:free": "Nex N2 Pro (FREE)",
    "nvidia/nemotron-3-nano-30b-a3b:free": "NVIDIA Nemotron Nano 30B (FREE)",
    "llama-3.3-70b-versatile": "Llama 3.3 70B (Groq)",
    "qwen/qwen3-32b": "Qwen3 32B (Groq)",
    "zai-glm-4.7": "GLM 4.7 (Cerebras)",
    "gpt-oss-120b": "GPT-OSS 120B (Cerebras)",
    "meta-llama/Llama-3.3-70B-Instruct-Turbo": "Llama 3.3 70B Turbo (Together)",
    "Meta-Llama-3.3-70B-Instruct": "Llama 3.3 70B (SambaNova)",
    "meta/llama-3.1-405b-instruct": "Llama 3.1 405B (NVIDIA NIM)",
    "Qwen/Qwen3.5-35B-A3B": "Qwen 3.5 35B (SiliconFlow)",
    "nex-agi/Nex-N2-Pro": "Nex N2 Pro (SiliconFlow)",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "DeepSeek R1 Distill 7B",
    "Qwen/Qwen2.5-Coder-32B-Instruct": "Qwen 2.5 Coder 32B",
    "meta-llama/Llama-3.3-70B-Instruct": "Llama 3.3 70B (HuggingFace)",
    "Llama-4-Scout-17B-16E": "Llama 4 Scout (GitHub)",
    "DeepSeek-R1": "DeepSeek R1 (GitHub/SambaNova)",
    "qwen-long": "Qwen Long (Alibaba)",
    "qwen-max": "Qwen Max (Alibaba)",
    "qwen-plus": "Qwen Plus (Alibaba)",
    "deepseek/deepseek-r1": "DeepSeek R1 (AIML API)",
    "google/gemini-2.5-flash": "Gemini 2.5 Flash (AIML API)",
    "nvidia/nemotron-3-ultra": "Nemotron Ultra (AIML API)",
    "deepseek-reasoner": "DeepSeek R1 (DeepSeek)",
    "Qwen/Qwen3-Coder-30B-Instruct": "Qwen3 Coder 30B (Together)",
    "llama-3.1-8b-instant": "Llama 3.1 8B Instant (Groq)",
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

LOW_COST_MODEL_OPTIONS: list[dict[str, str]] = [
    {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "label": "DeepSeek V3",
        "tier": "Best value",
        "cost": "$",
    },
    {
        "provider": "together",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "label": "Llama 3.3 70B Turbo",
        "tier": "Fast GPU",
        "cost": "$",
    },
]

FREE_MODEL_OPTIONS: list[dict[str, str]] = [
    {
        "provider": "openrouter",
        "model": "openai/gpt-oss-120b:free",
        "label": "OpenAI GPT-OSS 120B (FREE)",
        "tier": "Best JSON",
        "cost": "Free",
    },
    {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "label": "Gemini 2.5 Flash (FREE)",
        "tier": "Reasoning",
        "cost": "Free",
    },
    {
        "provider": "openrouter",
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "label": "NVIDIA Nemotron 3 Super (FREE)",
        "tier": "1M context",
        "cost": "Free",
    },
    {
        "provider": "openrouter",
        "model": "poolside/laguna-m.1:free",
        "label": "Poolside Laguna M.1 (FREE)",
        "tier": "Coding agent",
        "cost": "Free",
    },
    {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "label": "Llama 3.3 70B (Groq FREE)",
        "tier": "Fast",
        "cost": "Free",
    },
    {
        "provider": "openrouter",
        "model": "openrouter/owl-alpha",
        "label": "OpenRouter Owl Alpha (FREE)",
        "tier": "1.05M context",
        "cost": "Free",
    },
]


def model_display_name(model: str) -> str:
    """Return a human-readable model label."""
    return MODEL_DISPLAY_NAMES.get(model, model.split("/")[-1])


def chain_fallback_summary(routing: RoutingEntry, max_labels: int = 4) -> str:
    """Summarize fallback chain for admin UI."""
    labels: list[str] = []
    for idx in range(2, _MAX_CHAIN_MODELS + 1):
        entry = routing.get(f"model_{idx}")
        if not entry:
            break
        labels.append(model_display_name(entry[1]).replace(" (FREE)", ""))
        if len(labels) >= max_labels:
            remaining = sum(
                1 for j in range(idx + 1, _MAX_CHAIN_MODELS + 1) if routing.get(f"model_{j}")
            )
            if remaining:
                labels.append(f"+{remaining} more")
            break
    return " → ".join(labels) if labels else ""


def free_fallback_chain(task_type: str) -> str:
    """Summarize free-mode fallback chain for UI."""
    routing = FREE_ROUTING.get(task_type)
    if not routing:
        return ""
    return chain_fallback_summary(routing)


def low_cost_fallback_chain(task_type: str) -> str:
    """Summarize low-cost fallback chain for UI."""
    routing = LOW_COST_ROUTING.get(task_type)
    if not routing:
        return ""
    return chain_fallback_summary(routing)


def routing_for_tier(tier: str) -> dict[str, RoutingEntry]:
    """Return routing table for a cost tier."""
    if tier == "premium":
        return {}
    return TIER_ROUTING_TABLES.get(tier, FREE_ROUTING)
