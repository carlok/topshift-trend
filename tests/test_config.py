"""Tests for configuration parsing and environment loading."""

from __future__ import annotations

from pathlib import Path

from bot.config import AppConfig, load_config


def test_resolved_since_and_language_parsing() -> None:
    """Config should parse since and language from TRENDING_URL query params."""
    config = AppConfig(
        telegram_bot_token="token",
        trending_url="https://github.com/trending?since=weekly&l=python",
    )
    assert config.resolved_since() == "weekly"
    assert config.resolved_language() == "python"


def test_invalid_since_falls_back_to_monthly() -> None:
    """Invalid since query value should default to monthly."""
    config = AppConfig(
        telegram_bot_token="token",
        trending_url="https://github.com/trending?since=unknown",
    )
    assert config.resolved_since() == "monthly"


def test_normalized_log_level_defaults_to_info() -> None:
    """Unknown log level names should map to INFO."""
    config = AppConfig(telegram_bot_token="token", log_level="unknown")
    assert isinstance(config.normalized_log_level(), int)


def test_load_config_from_environment(monkeypatch) -> None:
    """Environment settings should be loaded into AppConfig."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setenv("CHECK_SCHEDULE_CRON", "5 7 * * *")
    monkeypatch.setenv("TRENDING_URL", "https://github.com/trending?since=daily")
    monkeypatch.setenv("TOP_N", "7")
    monkeypatch.setenv("DATA_DIR", "/tmp/topshift-data")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    config = load_config()
    assert config.telegram_bot_token == "bot-token"
    assert config.check_schedule_cron == "5 7 * * *"
    assert config.top_n == 7
    assert config.data_dir == Path("/tmp/topshift-data")
    assert config.log_level == "DEBUG"

