"""Application configuration via Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/core/config.py -> project root is three levels up
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from the project root ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(
        ...,
        description="Async PostgreSQL connection URL (postgresql+asyncpg://...).",
    )
    sync_database_url: str | None = Field(
        default=None,
        description="Sync PostgreSQL connection URL for Alembic (postgresql://...).",
    )
    redis_url: str = Field(
        ...,
        description="Redis connection URL.",
    )
    jwt_secret: str = Field(
        ...,
        min_length=32,
        description="Secret key for signing JWT tokens (minimum 32 characters).",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Algorithm used to sign JWT tokens.",
    )
    access_token_expire_minutes: int = Field(
        default=15,
        description="Access token lifetime in minutes.",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        description="Refresh token lifetime in days.",
    )
    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key for Claude (optional).",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key used as a fallback (optional).",
    )
    openrouter_api_key: str | None = Field(
        default=None,
        description="OpenRouter API key for free-tier model routing (optional).",
    )
    groq_api_key: str | None = Field(
        default=None,
        description="Groq API key — fast free LPU inference, 14,400 req/day (optional).",
    )
    together_api_key: str | None = Field(
        default=None,
        description="Together AI API key — GPU inference free tier (optional).",
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="Google Gemini API key — 1.5K req/day free, 250K TPM (optional).",
    )
    cerebras_api_key: str | None = Field(
        default=None,
        description="Cerebras API key — 1M tokens/day free, ultra-fast inference (optional).",
    )
    deepseek_api_key: str | None = Field(
        default=None,
        description="DeepSeek API key — low-cost V3 model ~$0.14/1M tokens (optional).",
    )
    sambanova_api_key: str | None = Field(
        default=None,
        description="SambaNova API key — free Llama 3.3 70B, 20-480 RPM (optional).",
    )
    nvidia_api_key: str | None = Field(
        default=None,
        description="NVIDIA NIM API key — free Llama 405B, 1K calls/month (optional).",
    )
    huggingface_api_key: str | None = Field(
        default=None,
        description="Hugging Face token — free inference via HF router (optional).",
    )
    aimlapi_api_key: str | None = Field(
        default=None,
        description="AIML API key — 500+ models pay-as-you-go (optional).",
    )
    siliconflow_api_key: str | None = Field(
        default=None,
        description="SiliconFlow API key — generous free tier (optional).",
    )
    alibaba_api_key: str | None = Field(
        default=None,
        description="Alibaba DashScope API key — Qwen models free trial (optional).",
    )
    github_api_key: str | None = Field(
        default=None,
        description="GitHub Models token — 150 RPD free open weights (optional).",
    )
    environment: str = Field(
        default="development",
        description="Runtime environment name (e.g. development, staging, production).",
    )
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3000"],
        description="CORS allowed origins (comma-separated in .env).",
    )
    r2_account_id: str | None = Field(
        default=None,
        description="Cloudflare R2 account ID.",
    )
    r2_access_key_id: str | None = Field(
        default=None,
        description="Cloudflare R2 access key ID.",
    )
    r2_secret_access_key: str | None = Field(
        default=None,
        description="Cloudflare R2 secret access key.",
    )
    r2_bucket_name: str | None = Field(
        default=None,
        description="Cloudflare R2 bucket name.",
    )
    r2_endpoint_url: str | None = Field(
        default=None,
        description="Cloudflare R2 S3-compatible endpoint URL.",
    )
    upload_dir: str = Field(
        default="uploads",
        description="Local upload directory when R2 is not configured.",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: str | list[str]) -> list[str]:
        """Parse a comma-separated string into a list of origins."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def derive_sync_database_url(self) -> Self:
        """Derive the sync database URL from the async URL when not explicitly set."""
        if self.sync_database_url is None:
            self.sync_database_url = self.database_url.replace(
                "postgresql+asyncpg://",
                "postgresql://",
                1,
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    The instance is created once and reused for the lifetime of the process.
    """
    return Settings()
