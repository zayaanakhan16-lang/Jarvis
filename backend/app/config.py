"""Application configuration.

Secrets are read from the environment only. Nothing here is ever exposed to the
browser; the frontend learns about credentials exclusively through the
``configured: true/false`` flags returned by the integrations API.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core --------------------------------------------------------------
    app_name: str = "JARVIS"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api"

    # --- Persistence -------------------------------------------------------
    # Defaults to SQLite so the platform runs with zero configuration.
    # Set DATABASE_URL=postgresql+asyncpg://user:pass@host/db for production.
    database_url: str = "sqlite+aiosqlite:///./jarvis.db"

    # --- HTTP --------------------------------------------------------------
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    request_timeout_seconds: float = 120.0

    # --- Model providers ---------------------------------------------------
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    deepseek_base_url: str | None = None
    mistral_base_url: str | None = None
    groq_base_url: str | None = None
    openrouter_base_url: str | None = None
    anthropic_base_url: str | None = None
    gemini_base_url: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    google_api_key: str | None = None
    deepseek_api_key: str | None = None
    mistral_api_key: str | None = None
    groq_api_key: str | None = None
    openrouter_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # --- Integrations ------------------------------------------------------
    openhands_api_key: str | None = None
    openhands_base_url: str = "https://app.all-hands.dev"
    opencode_base_url: str = "http://localhost:4096"
    github_token: str | None = None
    vercel_token: str | None = None
    railway_token: str | None = None
    elevenlabs_api_key: str | None = None
    tavily_api_key: str | None = None
    brave_api_key: str | None = None
    serper_api_key: str | None = None
    search_provider: str = "tavily"

    # --- Orchestration -----------------------------------------------------
    orchestrator_model: str | None = None
    max_parallel_tasks: int = 4
    task_timeout_seconds: float = 300.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_gemini_key(self) -> str | None:
        """Gemini is commonly configured as either GEMINI_API_KEY or GOOGLE_API_KEY."""
        return self.gemini_api_key or self.google_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
