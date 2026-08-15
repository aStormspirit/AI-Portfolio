from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_base_url: str | None = Field(
        default=None,
        description="Optional OpenAI-compatible API base URL (e.g. OpenRouter)",
    )
    llm_model: str = "gpt-4o-mini"
    max_pdf_size_mb: int = 5

    uploads_dir: Path = BASE_DIR / "uploads"
    outputs_dir: Path = BASE_DIR / "outputs"
    templates_dir: Path = BASE_DIR / "app" / "templates"

    @property
    def max_pdf_size_bytes(self) -> int:
        return self.max_pdf_size_mb * 1024 * 1024

    @property
    def resolved_openai_base_url(self) -> str | None:
        if self.openai_base_url:
            return self.openai_base_url.rstrip("/")
        # OpenRouter keys start with sk-or-
        if self.openai_api_key.startswith("sk-or-"):
            return OPENROUTER_BASE_URL
        return None


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    return settings
