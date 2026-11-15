"""Regression tests for python-telegram-bot startup on Python 3.13."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from telegram import Bot
from telegram.ext import Updater

from bot.config import AppConfig
from bot.main import TopShiftRuntime, build_application


def test_updater_construction_without_slots_error() -> None:
    """PTB 20.x sets __polling_cleanup_cb on Updater without a slot (breaks on 3.13)."""
    Updater(bot=Bot("123456:TEST"), update_queue=asyncio.Queue())


@pytest.mark.skipif(
    sys.version_info < (3, 13),
    reason="Production runtime image uses Python 3.13; guard the deployed interpreter.",
)
def test_build_application_constructs_real_telegram_application(tmp_path: Path) -> None:
    """Application.builder().build() must succeed with real PTB (no Application mocks)."""
    config = AppConfig(telegram_bot_token="123456:TEST", data_dir=tmp_path)
    application = build_application(config)

    assert application.bot.token == config.telegram_bot_token
    assert application.updater is not None
    runtime = application.bot_data.get("runtime")
    assert isinstance(runtime, TopShiftRuntime)
    assert len(application.handlers[0]) == 5
