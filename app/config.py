from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_RXRESUME_BASE_URL = "https://rxresu.me/api/openapi"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(
        default="",
        description="Token from @BotFather",
    )

    # LLM (adaptation to a job vacancy)
    openai_api_key: str = Field(
        default="",
        description="OpenAI or OpenRouter API key",
    )
    openai_base_url: str | None = Field(
        default=None,
        description="Optional OpenAI-compatible base URL (e.g. OpenRouter)",
    )
    llm_model: str = "gpt-4o-mini"

    # Cover letter (/message)
    cover_letter_temperature: float = Field(
        default=0.55,
        description="Sampling temperature for /message cover letters",
    )
    cover_letter_max_tokens: int = Field(
        default=900,
        description="Max tokens for cover letter generation",
    )
    cover_letter_golden_limit: int = Field(
        default=3,
        description="How many golden examples to include as few-shot for /message",
    )

    # Reactive Resume (rxresu.me) API
    rxresume_api_key: str = Field(
        default="",
        description="API key from rxresu.me → Settings → API Keys (x-api-key header)",
    )
    rxresume_base_url: str = Field(
        default=DEFAULT_RXRESUME_BASE_URL,
        description="API base URL. For self-hosted: https://<host>/api/openapi",
    )
    rxresume_ai_provider_id: str = Field(
        default="",
        description="Optional saved AI provider id used to parse the PDF",
    )

    # Limits
    max_pdf_size_mb: int = 15

    @property
    def max_pdf_size_bytes(self) -> int:
        return self.max_pdf_size_mb * 1024 * 1024

    @property
    def rxresume_api_base(self) -> str:
        return self.rxresume_base_url.rstrip("/")

    @property
    def resolved_openai_base_url(self) -> str | None:
        if self.openai_base_url:
            return self.openai_base_url.rstrip("/")
        # OpenRouter keys start with sk-or-
        if self.openai_api_key.startswith("sk-or-"):
            return OPENROUTER_BASE_URL
        return None

    @property
    def rxresume_app_base(self) -> str:
        """Public web host, derived by stripping the `/api/openapi` suffix."""
        base = self.rxresume_api_base
        for suffix in ("/api/openapi", "/api"):
            if base.endswith(suffix):
                return base[: -len(suffix)]
        return base


@lru_cache
def get_settings() -> Settings:
    return Settings()
