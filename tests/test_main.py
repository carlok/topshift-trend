"""Tests for runtime and Telegram command handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.config import AppConfig
from bot.main import (
    TopShiftRuntime,
    cmd_check,
    cmd_help,
    cmd_start,
    cmd_stop,
    cmd_top,
    post_init,
    post_shutdown,
    run_scheduled_check,
)
from bot.scraper import TrendingRepo


def _repo(owner: str, repo: str) -> TrendingRepo:
    return TrendingRepo(
        owner=owner,
        repo=repo,
        stars=10,
        description="desc",
        url=f"https://github.com/{owner}/{repo}",
    )


@dataclass
class DummyChat:
    """Minimal chat object with id only."""

    id: int


@dataclass
class DummyUpdate:
    """Minimal update object for command handlers."""

    effective_chat: DummyChat | None


class DummyBot:
    """Minimal async bot to capture outgoing messages."""

    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        disable_web_page_preview: bool = False,
    ) -> None:
        self.messages.append((chat_id, text))


class DummyContext:
    """Minimal context object for command handlers."""

    def __init__(self, runtime: TopShiftRuntime, bot: DummyBot) -> None:
        self.application = type("App", (), {"bot_data": {"runtime": runtime}})()
        self.bot = bot


class DummyScheduler:
    """Track scheduler lifecycle interactions."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.jobs: list[dict[str, Any]] = []

    def add_job(
        self,
        func: Any,
        trigger: Any,
        kwargs: dict[str, Any],
        id: str,
        replace_existing: bool,
    ) -> None:
        self.jobs.append(
            {
                "func": func,
                "trigger": trigger,
                "kwargs": kwargs,
                "id": id,
                "replace_existing": replace_existing,
            }
        )

    def start(self) -> None:
        self.started = True

    def shutdown(self, wait: bool = False) -> None:
        self.stopped = True


async def test_runtime_run_check_persists(monkeypatch, tmp_path: Path) -> None:
    """Runtime run_check should save state and return current/new repositories."""
    config = AppConfig(telegram_bot_token="token", data_dir=tmp_path, top_n=2)
    runtime = TopShiftRuntime(config)
    async def fake_fetch_top(*args: Any, **kwargs: Any) -> list[TrendingRepo]:
        return [_repo("one", "a"), _repo("two", "b")]

    monkeypatch.setattr(
        "bot.main.fetch_top_repositories",
        fake_fetch_top,
    )

    result = await runtime.run_check()
    assert len(result.current) == 2
    assert len(result.new_entries) == 2
    assert runtime.store.load_state() is not None


async def test_start_stop_check_top_commands(monkeypatch, tmp_path: Path) -> None:
    """Handlers should send expected messages for lifecycle commands."""
    config = AppConfig(telegram_bot_token="token", data_dir=tmp_path)
    runtime = TopShiftRuntime(config)
    bot = DummyBot()
    context = DummyContext(runtime=runtime, bot=bot)
    update = DummyUpdate(effective_chat=DummyChat(id=123))

    async def fake_fetch_top(*args: Any, **kwargs: Any) -> list[TrendingRepo]:
        return [_repo("owner", "repo")]

    monkeypatch.setattr(
        "bot.main.fetch_top_repositories",
        fake_fetch_top,
    )

    await cmd_start(update, context)
    assert any("Subscribed" in message for _, message in bot.messages)
    assert runtime.store.load_subscribers() == {123}

    await cmd_check(update, context)
    assert any(
        "new entry" in message or "No new repositories" in message
        for _, message in bot.messages
    )

    await cmd_top(update, context)
    assert any("Current GitHub Trending Top list" in message for _, message in bot.messages)

    await cmd_help(update, context)
    assert any("Available commands" in message for _, message in bot.messages)

    await cmd_stop(update, context)
    assert runtime.store.load_subscribers() == set()


async def test_scheduled_check_notifies(monkeypatch, tmp_path: Path) -> None:
    """Scheduled check should notify subscribers for new entries."""
    config = AppConfig(telegram_bot_token="token", data_dir=tmp_path)
    runtime = TopShiftRuntime(config)
    runtime.store.save_subscribers({1})

    async def fake_fetch_top(*args: Any, **kwargs: Any) -> list[TrendingRepo]:
        return [_repo("new", "repo")]

    monkeypatch.setattr("bot.main.fetch_top_repositories", fake_fetch_top)
    app = type("App", (), {"bot_data": {"runtime": runtime}, "bot": DummyBot()})()
    await run_scheduled_check(app)
    assert app.bot.messages


async def test_scheduler_hooks(monkeypatch, tmp_path: Path) -> None:
    """post_init and post_shutdown should start and stop scheduler."""
    config = AppConfig(telegram_bot_token="token", data_dir=tmp_path)
    runtime = TopShiftRuntime(config)
    async def fake_set_my_commands(commands: list[Any]) -> None:
        return None

    app = type(
        "App",
        (),
        {
            "bot_data": {"runtime": runtime},
            "bot": type(
                "Bot",
                (),
                {"set_my_commands": staticmethod(fake_set_my_commands)},
            )(),
        },
    )()
    scheduler = DummyScheduler()
    monkeypatch.setattr("bot.main.AsyncIOScheduler", lambda: scheduler)

    await post_init(app)
    assert scheduler.started is True
    assert runtime.scheduler is scheduler

    await post_shutdown(app)
    assert scheduler.stopped is True

