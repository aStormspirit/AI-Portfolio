from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_RXRESUME_BASE_URL = "https://rxresu.me/api/openapi"


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
