"""Schemas for AI configuration admin API."""

from pydantic import BaseModel, Field


class FreeModeUpdate(BaseModel):
    enabled: bool


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


class AiConfigResponse(BaseModel):
    free_mode_enabled: bool
    providers: list[ProviderStatus]
    paid_routing: list[RoutingRow]
    free_routing: list[RoutingRow]
    screen_overrides: dict[str, dict[str, str]]
    screen_models: list[ScreenModelInfo] = Field(default_factory=list)
    paid_model_options: list[dict[str, str]] = Field(default_factory=list)
    free_model_options: list[dict[str, str]] = Field(default_factory=list)
