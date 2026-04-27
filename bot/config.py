"""Configuration management for the TopShift bot."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs, urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

VALID_SINCE_VALUES: set[str] = {"daily", "weekly", "monthly"}
DEFAULT_LOG_LEVEL: Final[int] = logging.INFO


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration loaded from environment variables."""

    telegram_bot_token: str
    check_schedule_cron: str = "0 8 * * *"
    trending_url: str = "https://github.com/trending?since=monthly"
    top_n: int = 10
    data_dir: Path = Path("/data")
    log_level: str = "INFO"

    def resolved_since(self) -> str:
        """Return the trending time window derived from TRENDING_URL."""
        query = parse_qs(urlparse(self.trending_url).query)
        raw_since = (query.get("since", ["monthly"])[0] or "monthly").lower()
        return raw_since if raw_since in VALID_SINCE_VALUES else "monthly"

    def resolved_language(self) -> str | None:
        """Return optional language filter from TRENDING_URL query."""
        query = parse_qs(urlparse(self.trending_url).query)
        language = (query.get("l", [""])[0] or "").strip().lower()
        return language or None

    def normalized_log_level(self) -> int:
        """Convert configured log level name to the logging module value."""
        level_map = logging.getLevelNamesMapping()
        return int(level_map.get(self.log_level.upper(), DEFAULT_LOG_LEVEL))


class EnvironmentSettings(BaseSettings):
    """Environment-backed settings model."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    check_schedule_cron: str = "0 8 * * *"
    trending_url: str = "https://github.com/trending?since=monthly"
    top_n: int = 10
    data_dir: Path = Path("/data")
    log_level: str = "INFO"


def load_config() -> AppConfig:
    """Load and validate application settings from the environment."""
    settings = EnvironmentSettings()  # type: ignore[call-arg]
    return AppConfig(
        telegram_bot_token=settings.telegram_bot_token,
        check_schedule_cron=settings.check_schedule_cron,
        trending_url=settings.trending_url,
        top_n=settings.top_n,
        data_dir=settings.data_dir,
        log_level=settings.log_level,
    )

