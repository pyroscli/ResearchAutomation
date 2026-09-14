from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str
    cursor_api_key: str
    cursor_model: str = "composer-2.5"
    database_url: str = (
        "postgresql+asyncpg://researchbot:researchbot@127.0.0.1:5432/researchbot"
    )

    playbook_dir: Path | None = None
    playbook_repo_url: str | None = None
    playbook_repo_ref: str = "main"

    research_timeout_seconds: int = Field(default=720, ge=60, le=3600)
    max_query_length: int = Field(default=2000, ge=20, le=8000)
    max_concurrent_global: int = Field(default=5, ge=1, le=50)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_playbook_dir(settings: Settings) -> Path:
    if settings.playbook_dir is not None:
        return settings.playbook_dir
    for candidate in (repo_root() / "playbook", Path.cwd() / "playbook"):
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("playbook/ directory not found")
