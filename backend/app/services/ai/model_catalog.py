"""AI model catalog — all PM Studio models grouped by cost tier."""

from __future__ import annotations

from typing import Any, TypedDict

from app.services.ai.providers import (
    DEFAULT_PAID_ROUTING,
    FREE_ROUTING,
    LOW_COST_ROUTING,
    MODEL_DISPLAY_NAMES,
    model_display_name,
)

CostTier = str  # "free" | "low_cost" | "premium"


class ModelCatalogEntry(TypedDict, total=False):
    provider: str
    model: str
    label: str
    tier: CostTier
    cost: str
    context: str
    note: str
    task_types: list[str]
    in_routing: bool
    available: bool


class ProviderMeta(TypedDict, total=False):
    label: str
    signup_url: str
    docs_url: str
    default_tier: CostTier
    note: str


PROVIDER_META: dict[str, ProviderMeta] = {
    "anthropic": {
        "label": "Anthropic (Claude)",
        "signup_url": "https://console.anthropic.com/settings/keys",
        "default_tier": "premium",
        "note": "Premium tier — best quality for client deliverables.",
    },
    "openai": {
        "label": "OpenAI (GPT)",
        "signup_url": "https://platform.openai.com/api-keys",
        "default_tier": "premium",
    },
    "openrouter": {
        "label": "OpenRouter",
        "signup_url": "https://openrouter.ai/keys",
        "default_tier": "free",
        "note": "~200 req/hour on :free models; 1,000 req/day with credits.",
    },
    "groq": {
        "label": "Groq",
        "signup_url": "https://console.groq.com/keys",
        "default_tier": "free",
        "note": "14,400 req/day — ultra-fast LPU inference.",
    },
    "gemini": {
        "label": "Google Gemini",
        "signup_url": "https://aistudio.google.com/apikey",
        "default_tier": "free",
        "note": "1,500 req/day on Gemini 2.5 Flash.",
    },
    "cerebras": {
        "label": "Cerebras",
        "signup_url": "https://cloud.cerebras.ai",
        "default_tier": "free",
        "note": "1M tokens/day; 8K context cap on free tier.",
    },
    "deepseek": {
        "label": "DeepSeek",
        "signup_url": "https://platform.deepseek.com",
        "default_tier": "low_cost",
        "note": "~$0.14/1M tokens — primary low-cost model.",
    },
    "together": {
        "label": "Together AI",
        "signup_url": "https://api.together.xyz/settings/api-keys",
        "default_tier": "low_cost",
        "note": "$25 free startup credit + zero-cost open models.",
    },
    "sambanova": {
        "label": "SambaNova Cloud",
        "signup_url": "https://cloud.sambanova.ai",
        "default_tier": "free",
        "note": "20–480 RPM free tier.",
    },
    "nvidia": {
        "label": "NVIDIA NIM",
        "signup_url": "https://build.nvidia.com",
        "default_tier": "free",
        "note": "~1,000 free calls/month.",
    },
    "huggingface": {
        "label": "Hugging Face",
        "signup_url": "https://huggingface.co/settings/tokens",
        "default_tier": "free",
        "note": "Free inference via HF router; rate limits apply.",
    },
    "aimlapi": {
        "label": "AIML API",
        "signup_url": "https://aimlapi.com/",
        "default_tier": "low_cost",
        "note": "500+ models, pay-as-you-go from $20 prepaid.",
    },
    "siliconflow": {
        "label": "SiliconFlow",
        "signup_url": "https://cloud.siliconflow.com/",
        "default_tier": "free",
        "note": "Generous free tier — up to 10,000+ req/day on verified accounts.",
    },
    "alibaba": {
        "label": "Alibaba Cloud (DashScope)",
        "signup_url": "https://www.alibabacloud.com/en/free",
        "default_tier": "free",
        "note": "Free trial credits on Model Studio / Qwen models.",
    },
    "github": {
        "label": "GitHub Models",
        "signup_url": "https://github.com/marketplace/models",
        "default_tier": "free",
        "note": "15 RPM / 150 RPD for most public open weights.",
    },
}

# Explicit tier overrides for models that differ from their provider default.
_MODEL_TIER_OVERRIDES: dict[tuple[str, str], CostTier] = {}

# Provider-native model catalogs (shown in admin even when not yet in routing chains).
PROVIDER_MODEL_CATALOG: dict[str, list[dict[str, str]]] = {
    "anthropic": [
        {"model": "claude-sonnet-4-5", "label": "Claude Sonnet 4.5", "tier": "premium", "cost": "$$$", "context": "200K"},
        {"model": "claude-haiku-4-5", "label": "Claude Haiku 4.5", "tier": "premium", "cost": "$", "context": "200K"},
    ],
    "openai": [
        {"model": "gpt-4o", "label": "GPT-4o", "tier": "premium", "cost": "$$", "context": "128K"},
        {"model": "gpt-4o-mini", "label": "GPT-4o Mini", "tier": "low_cost", "cost": "$", "context": "128K"},
    ],
    "openrouter": [
        {"model": "openai/gpt-oss-120b:free", "label": "GPT-OSS 120B", "tier": "free", "cost": "Free", "context": "131K"},
        {"model": "openai/gpt-oss-20b:free", "label": "GPT-OSS 20B", "tier": "free", "cost": "Free", "context": "131K"},
        {"model": "openrouter/owl-alpha", "label": "Owl Alpha", "tier": "free", "cost": "Free", "context": "1.05M"},
        {"model": "nvidia/nemotron-3-ultra-550b-a55b:free", "label": "Nemotron Ultra 550B", "tier": "free", "cost": "Free", "context": "1M"},
        {"model": "nvidia/nemotron-3-super-120b-a12b:free", "label": "Nemotron Super 120B", "tier": "free", "cost": "Free", "context": "1M"},
        {"model": "nvidia/nemotron-3-nano-30b-a3b:free", "label": "Nemotron Nano 30B", "tier": "free", "cost": "Free", "context": "256K"},
        {"model": "poolside/laguna-m.1:free", "label": "Laguna M.1", "tier": "free", "cost": "Free", "context": "262K"},
        {"model": "poolside/laguna-xs.2:free", "label": "Laguna XS.2", "tier": "free", "cost": "Free", "context": "262K"},
        {"model": "nex-agi/nex-n2-pro:free", "label": "Nex N2 Pro", "tier": "free", "cost": "Free", "context": "262K"},
        {"model": "google/gemma-4-31b-it:free", "label": "Gemma 4 31B", "tier": "free", "cost": "Free", "context": "256K"},
        {"model": "google/gemma-4-26b-a4b-it:free", "label": "Gemma 4 26B MoE", "tier": "free", "cost": "Free", "context": "256K"},
        {"model": "moonshotai/kimi-k2.6:free", "label": "Kimi K2.6", "tier": "free", "cost": "Free", "context": "256K"},
        {"model": "meta-llama/llama-4-scout:free", "label": "Llama 4 Scout", "tier": "free", "cost": "Free", "context": "128K"},
        {"model": "qwen/qwen3.6-plus:free", "label": "Qwen 3.6 Plus", "tier": "free", "cost": "Free", "context": "256K"},
    ],
    "groq": [
        {"model": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B", "tier": "free", "cost": "Free", "context": "128K"},
        {"model": "llama-3.1-8b-instant", "label": "Llama 3.1 8B Instant", "tier": "free", "cost": "Free", "context": "128K"},
        {"model": "gemma2-9b-it", "label": "Gemma 2 9B", "tier": "free", "cost": "Free", "context": "8K"},
        {"model": "qwen/qwen3-32b", "label": "Qwen3 32B", "tier": "free", "cost": "Free", "context": "128K"},
    ],
    "gemini": [
        {"model": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "tier": "free", "cost": "Free", "context": "1M"},
        {"model": "gemini-2.0-flash", "label": "Gemini 2.0 Flash", "tier": "free", "cost": "Free", "context": "1M"},
        {"model": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite", "tier": "free", "cost": "Free", "context": "1M"},
    ],
    "cerebras": [
        {"model": "zai-glm-4.7", "label": "GLM 4.7", "tier": "free", "cost": "Free", "context": "8K"},
        {"model": "gpt-oss-120b", "label": "GPT-OSS 120B", "tier": "free", "cost": "Free", "context": "8K"},
        {"model": "llama-3.3-70b", "label": "Llama 3.3 70B", "tier": "free", "cost": "Free", "context": "8K"},
    ],
    "deepseek": [
        {"model": "deepseek-chat", "label": "DeepSeek V3", "tier": "low_cost", "cost": "$", "context": "128K"},
        {"model": "deepseek-reasoner", "label": "DeepSeek R1", "tier": "low_cost", "cost": "$$", "context": "128K"},
    ],
    "together": [
        {"model": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "label": "Llama 3.3 70B Turbo", "tier": "low_cost", "cost": "$", "context": "128K"},
        {"model": "Qwen/Qwen3-Coder-30B-Instruct", "label": "Qwen3 Coder 30B", "tier": "low_cost", "cost": "$", "context": "128K"},
        {"model": "mistralai/Mistral-Small-4", "label": "Mistral Small 4", "tier": "low_cost", "cost": "$", "context": "128K"},
    ],
    "sambanova": [
        {"model": "Meta-Llama-3.3-70B-Instruct", "label": "Llama 3.3 70B", "tier": "free", "cost": "Free", "context": "128K"},
        {"model": "DeepSeek-R1", "label": "DeepSeek R1", "tier": "free", "cost": "Free", "context": "128K"},
    ],
    "nvidia": [
        {"model": "meta/llama-3.1-405b-instruct", "label": "Llama 3.1 405B", "tier": "free", "cost": "Free", "context": "128K"},
        {"model": "nvidia/llama-3.1-nemotron-70b", "label": "Nemotron 70B", "tier": "free", "cost": "Free", "context": "128K"},
    ],
    "huggingface": [
        {"model": "meta-llama/Llama-3.3-70B-Instruct", "label": "Llama 3.3 70B", "tier": "free", "cost": "Free", "context": "128K"},
        {"model": "Qwen/Qwen2.5-Coder-32B-Instruct", "label": "Qwen 2.5 Coder 32B", "tier": "free", "cost": "Free", "context": "128K"},
        {"model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "label": "DeepSeek R1 Distill 7B", "tier": "free", "cost": "Free", "context": "32K"},
    ],
    "aimlapi": [
        {"model": "deepseek/deepseek-r1", "label": "DeepSeek R1", "tier": "low_cost", "cost": "$", "context": "128K"},
        {"model": "google/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "tier": "low_cost", "cost": "$", "context": "1M"},
        {"model": "openai/gpt-4o", "label": "GPT-4o", "tier": "premium", "cost": "$$", "context": "128K"},
        {"model": "anthropic/claude-sonnet-4-5", "label": "Claude Sonnet 4.5", "tier": "premium", "cost": "$$$", "context": "200K"},
        {"model": "nvidia/nemotron-3-ultra", "label": "Nemotron 3 Ultra", "tier": "low_cost", "cost": "$", "context": "1M"},
    ],
    "siliconflow": [
        {"model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "label": "DeepSeek R1 Distill 7B", "tier": "free", "cost": "Free", "context": "32K"},
        {"model": "Qwen/Qwen3.5-35B-A3B", "label": "Qwen 3.5 35B A3B", "tier": "free", "cost": "Free", "context": "256K"},
        {"model": "nex-agi/Nex-N2-Pro", "label": "Nex N2 Pro", "tier": "free", "cost": "Free", "context": "256K"},
    ],
    "alibaba": [
        {"model": "qwen-max", "label": "Qwen Max", "tier": "low_cost", "cost": "$", "context": "128K"},
        {"model": "qwen-plus", "label": "Qwen Plus", "tier": "low_cost", "cost": "$", "context": "128K"},
        {"model": "qwen-turbo", "label": "Qwen Turbo", "tier": "free", "cost": "Free", "context": "128K"},
        {"model": "qwen-long", "label": "Qwen Long", "tier": "low_cost", "cost": "$", "context": "1M"},
    ],
    "github": [
        {"model": "Llama-4-Scout-17B-16E", "label": "Llama 4 Scout 17B", "tier": "free", "cost": "Free", "context": "128K"},
        {"model": "DeepSeek-R1", "label": "DeepSeek R1", "tier": "free", "cost": "Free", "context": "128K"},
        {"model": "gpt-4o", "label": "GPT-4o", "tier": "premium", "cost": "$$", "context": "128K"},
    ],
}


def _infer_tier(provider: str, model: str) -> CostTier:
    key = (provider, model)
    if key in _MODEL_TIER_OVERRIDES:
        return _MODEL_TIER_OVERRIDES[key]
    if model.endswith(":free") or "(FREE)" in model_display_name(model):
        return "free"
    meta = PROVIDER_META.get(provider, {})
    default = meta.get("default_tier", "free")
    return default  # type: ignore[return-value]


def _cost_for_tier(tier: CostTier) -> str:
    return {"free": "Free", "low_cost": "$", "premium": "$$$"}.get(tier, "")


def _extract_routing_models() -> dict[tuple[str, str], set[str]]:
    """Map (provider, model) → task types where it appears in any routing table."""
    task_map: dict[tuple[str, str], set[str]] = {}

    def add_from_table(table: dict, tier_label: str) -> None:
        for task_type, entry in table.items():
            for idx in range(1, 21):
                pair = entry.get(f"model_{idx}")
                if not pair:
                    break
                provider, model = pair
                key = (provider, model)
                task_map.setdefault(key, set()).add(task_type)

    add_from_table(FREE_ROUTING, "free")
    add_from_table(LOW_COST_ROUTING, "low_cost")
    for task_type, (provider, model) in DEFAULT_PAID_ROUTING.items():
        task_map.setdefault((provider, model), set()).add(task_type)

    return task_map


def _entry_from_catalog_item(
    provider: str,
    item: dict[str, str],
    *,
    task_types: set[str],
    available: bool,
) -> ModelCatalogEntry:
    model = item["model"]
    tier = item.get("tier") or _infer_tier(provider, model)
    label = item.get("label") or model_display_name(model)
    return ModelCatalogEntry(
        provider=provider,
        model=model,
        label=label,
        tier=tier,  # type: ignore[typeddict-item]
        cost=item.get("cost") or _cost_for_tier(tier),  # type: ignore[arg-type]
        context=item.get("context", ""),
        note=item.get("note", ""),
        task_types=sorted(task_types),
        in_routing=bool(task_types),
        available=available,
    )


def build_full_model_catalog(
    available_providers: set[str] | None = None,
) -> dict[str, list[ModelCatalogEntry]]:
    """All PM Studio models grouped by tier (free / low_cost / premium)."""
    available = available_providers or set()
    routing_tasks = _extract_routing_models()
    seen: set[tuple[str, str]] = set()
    by_tier: dict[str, list[ModelCatalogEntry]] = {
        "free": [],
        "low_cost": [],
        "premium": [],
    }

    def add_entry(entry: ModelCatalogEntry) -> None:
        key = (entry["provider"], entry["model"])
        if key in seen:
            return
        seen.add(key)
        tier = entry.get("tier", "free")
        if tier not in by_tier:
            tier = "free"
        by_tier[tier].append(entry)

    # Provider-native catalogs first (richest metadata).
    for provider, items in PROVIDER_MODEL_CATALOG.items():
        for item in items:
            model = item["model"]
            tasks = routing_tasks.get((provider, model), set())
            add_entry(
                _entry_from_catalog_item(
                    provider,
                    item,
                    task_types=tasks,
                    available=provider in available,
                )
            )

    # Routing-only models not already in provider catalogs.
    for (provider, model), tasks in routing_tasks.items():
        if (provider, model) in seen:
            continue
        tier = _infer_tier(provider, model)
        add_entry(
            ModelCatalogEntry(
                provider=provider,
                model=model,
                label=model_display_name(model),
                tier=tier,
                cost=_cost_for_tier(tier),
                context="",
                note="Used in PM Studio routing chains",
                task_types=sorted(tasks),
                in_routing=True,
                available=provider in available,
            )
        )

    for tier in by_tier:
        by_tier[tier].sort(key=lambda e: (e["provider"], e["label"]))

    return by_tier


def build_configured_model_catalog(
    available_providers: set[str],
) -> dict[str, list[ModelCatalogEntry]]:
    """Models reachable only through providers that have API keys configured."""
    full = build_full_model_catalog(available_providers)
    return {
        tier: [m for m in models if m.get("available")]
        for tier, models in full.items()
    }


def flatten_catalog(catalog: dict[str, list[ModelCatalogEntry]]) -> list[dict[str, Any]]:
    """Flat list for dropdowns and API responses."""
    result: list[dict[str, Any]] = []
    for tier, models in catalog.items():
        for m in models:
            subtitle = m.get("context") or ("Routing" if m.get("in_routing") else "")
            result.append(
                {
                    **m,
                    "group": tier,
                    "tier": subtitle,
                }
            )
    return result


def catalog_to_model_options(
    catalog: dict[str, list[ModelCatalogEntry]],
    tier: CostTier,
) -> list[dict[str, str | bool]]:
    """Options shaped for ScreenModelSelector dropdowns."""
    opts: list[dict[str, str | bool]] = []
    for entry in catalog.get(tier, []):
        subtitle = entry.get("context") or ("Routing" if entry.get("in_routing") else "")
        opts.append(
            {
                "provider": entry["provider"],
                "model": entry["model"],
                "label": entry["label"],
                "tier": subtitle,
                "cost": entry["cost"],
                "context": entry.get("context", ""),
                "available": bool(entry.get("available", False)),
                "group": tier,
            }
        )
    return opts
