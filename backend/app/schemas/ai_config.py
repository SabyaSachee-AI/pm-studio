"""Schemas for AI configuration admin API."""

from pydantic import BaseModel, Field


class FreeModeUpdate(BaseModel):
    enabled: bool


class AiTierUpdate(BaseModel):
    tier: str  # "free" | "low_cost" | "premium"


class ScreenOverrideUpdate(BaseModel):
    screen: str
    provider: str | None = None
    model: str | None = None


class ProviderConfigUpdate(BaseModel):
    provider: str
    api_key: str | None = None
    is_enabled: bool | None = None


class ProviderStatus(BaseModel):
    provider: str
    configured: bool
    is_enabled: bool
    masked_key: str | None = None
    label: str = ""
    signup_url: str | None = None
    note: str | None = None
    default_tier: str = "free"


class GithubConfigUpdate(BaseModel):
    token: str | None = None
    owner: str | None = None


class GithubConfigStatus(BaseModel):
    configured: bool = False
    masked_token: str | None = None
    owner: str | None = None
    source: str = "none"  # "db" | "env" | "none"


class VpsConfigUpdate(BaseModel):
    host: str | None = None
    user: str | None = None
    ssh_key: str | None = None
    path: str | None = None


class VpsConfigStatus(BaseModel):
    configured: bool = False
    host: str | None = None
    user: str | None = None
    path: str | None = None
    has_key: bool = False


class ModelCatalogEntry(BaseModel):
    provider: str
    model: str
    label: str
    tier: str
    cost: str = ""
    context: str = ""
    note: str = ""
    task_types: list[str] = Field(default_factory=list)
    in_routing: bool = False
    available: bool = False


class TierModelCatalog(BaseModel):
    free: list[ModelCatalogEntry] = Field(default_factory=list)
    low_cost: list[ModelCatalogEntry] = Field(default_factory=list)
    premium: list[ModelCatalogEntry] = Field(default_factory=list)


class ProviderUsage(BaseModel):
    requests: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    requests_limit: int = 0
    tokens_limit: int = 0
    label: str = ""
    color: str = "gray"


class RoutingRow(BaseModel):
    task_type: str
    task_label: str
    quality_stars: int
    primary_model: str
    fallback_chain: str
    quality_note: str | None = None


class ScreenModelInfo(BaseModel):
    screen: str
    provider: str
    model: str
    label: str
    source: str


class ModelOption(BaseModel):
    provider: str
    model: str
    label: str
    tier: str = ""
    cost: str = ""
    context: str = ""
    available: bool = False
    group: str = ""


class AiConfigResponse(BaseModel):
    ai_tier: str
    free_mode_enabled: bool
    providers: list[ProviderStatus]
    paid_routing: list[RoutingRow]
    free_routing: list[RoutingRow]
    low_cost_routing: list[RoutingRow] = Field(default_factory=list)
    screen_overrides: dict[str, dict[str, str]]
    screen_models: list[ScreenModelInfo] = Field(default_factory=list)
    paid_model_options: list[ModelOption] = Field(default_factory=list)
    free_model_options: list[ModelOption] = Field(default_factory=list)
    low_cost_model_options: list[ModelOption] = Field(default_factory=list)
    daily_usage: dict[str, ProviderUsage] = Field(default_factory=dict)
    model_catalog: TierModelCatalog = Field(default_factory=TierModelCatalog)
    configured_model_catalog: TierModelCatalog = Field(default_factory=TierModelCatalog)
