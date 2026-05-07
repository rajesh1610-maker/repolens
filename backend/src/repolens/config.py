from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://repolens:repolens@localhost:5435/repolens"
    )
    cors_origins: str = "http://localhost:3003"
    log_level: str = "INFO"
    github_pat: str | None = None
    anthropic_api_key: str | None = None
    repolens_encryption_key: str | None = None

    # Scheduler (D5): default off in dev where uvicorn --reload would
    # restart the scheduler on every code change. Compose / production
    # turn this on explicitly.
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = 30
    sync_watchdog_minutes: int = 15

    # Phase 8: weekly digest. Opus 4.7 is the default — adaptive thinking
    # only, ~$5/M in / $25/M out. Switch to claude-haiku-4-5 for cheap
    # local iteration; the cost table in services/anthropic_client.py
    # covers both.
    digest_model: str = "claude-opus-4-7"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
