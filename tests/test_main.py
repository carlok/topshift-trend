"""Tests for runtime and Telegram command handlers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.config import AppConfig
from bot.main import (
    CheckResult,
    TopShiftRuntime,
    build_application,
    cmd_check,
    cmd_help,
    cmd_start,
    cmd_stop,
    cmd_top,
    configure_logging,
    main,
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


async def test_run_scheduled_check_handles_runtime_failure(tmp_path: Path) -> None:
    """Scheduled check should swallow runtime errors and keep loop alive."""
    config = AppConfig(telegram_bot_token="token", data_dir=tmp_path)
    runtime = TopShiftRuntime(config)

    async def fail_check() -> CheckResult:
        raise RuntimeError("boom")

    runtime.run_check = fail_check  # type: ignore[method-assign]
    app = type("App", (), {"bot_data": {"runtime": runtime}, "bot": DummyBot()})()

    await run_scheduled_check(app)
    assert app.bot.messages == []


async def test_handlers_ignore_updates_without_chat(tmp_path: Path) -> None:
    """Commands should no-op when effective_chat is absent."""
    config = AppConfig(telegram_bot_token="token", data_dir=tmp_path)
    runtime = TopShiftRuntime(config)
    bot = DummyBot()
    context = DummyContext(runtime=runtime, bot=bot)
    update = DummyUpdate(effective_chat=None)

    await cmd_start(update, context)
    await cmd_help(update, context)
    await cmd_stop(update, context)
    await cmd_top(update, context)
    await cmd_check(update, context)

    assert bot.messages == []


async def test_cmd_top_failure_reports_error(monkeypatch, tmp_path: Path) -> None:
    """When top fetch fails, handler should send a clear error message."""
    config = AppConfig(telegram_bot_token="token", data_dir=tmp_path)
    runtime = TopShiftRuntime(config)
    bot = DummyBot()
    context = DummyContext(runtime=runtime, bot=bot)
    update = DummyUpdate(effective_chat=DummyChat(id=321))

    async def failing_fetch(*args: Any, **kwargs: Any) -> list[TrendingRepo]:
        raise RuntimeError("network")

    monkeypatch.setattr("bot.main.fetch_top_repositories", failing_fetch)
    await cmd_top(update, context)

    assert bot.messages[-1] == (321, "Failed to fetch current top list.")


async def test_cmd_check_new_entries_summary(tmp_path: Path) -> None:
    """Immediate check should list each newly entered repository."""
    config = AppConfig(telegram_bot_token="token", data_dir=tmp_path)
    runtime = TopShiftRuntime(config)
    bot = DummyBot()
    context = DummyContext(runtime=runtime, bot=bot)
    update = DummyUpdate(effective_chat=DummyChat(id=111))

    async def fake_check() -> CheckResult:
        current = [_repo("a", "r1"), _repo("b", "r2")]
        return CheckResult(current=current, new_entries=current)

    runtime.run_check = fake_check  # type: ignore[method-assign]
    await cmd_check(update, context)

    assert "Found 2 new entries" in bot.messages[-1][1]
    assert "- a/r1" in bot.messages[-1][1]
    assert "- b/r2" in bot.messages[-1][1]


def test_configure_logging_sets_transport_loggers(tmp_path: Path) -> None:
    """Logging setup should force noisy HTTP transport logs to WARNING."""
    config = AppConfig(telegram_bot_token="token", data_dir=tmp_path, log_level="DEBUG")
    configure_logging(config)
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_build_application_registers_runtime_and_handlers(monkeypatch, tmp_path: Path) -> None:
    """Application factory should register runtime and command handlers."""
    config = AppConfig(telegram_bot_token="123456:ABCDEF", data_dir=tmp_path)

    class FakeApplication:
        def __init__(self) -> None:
            self.bot_data: dict[str, Any] = {}
            self.handlers: list[Any] = []

        def add_handler(self, handler: Any) -> None:
            self.handlers.append(handler)

    class FakeBuilder:
        def __init__(self) -> None:
            self.token_value = ""
            self.post_init_fn: Any = None
            self.post_shutdown_fn: Any = None

        def token(self, token: str) -> FakeBuilder:
            self.token_value = token
            return self

        def post_init(self, fn: Any) -> FakeBuilder:
            self.post_init_fn = fn
            return self

        def post_shutdown(self, fn: Any) -> FakeBuilder:
            self.post_shutdown_fn = fn
            return self

        def build(self) -> FakeApplication:
            return FakeApplication()

    class FakeApplicationFactory:
        @staticmethod
        def builder() -> FakeBuilder:
            return FakeBuilder()

    monkeypatch.setattr("bot.main.Application", FakeApplicationFactory)
    application = build_application(config)

    runtime = application.bot_data.get("runtime")
    assert isinstance(runtime, TopShiftRuntime)
    assert len(application.handlers) == 5


def test_main_bootstraps_and_runs(monkeypatch, tmp_path: Path) -> None:
    """Process entrypoint should load config, build app, and start polling."""
    config = AppConfig(telegram_bot_token="token", data_dir=tmp_path)
    called: dict[str, bool] = {"configured": False, "ran": False}

    def fake_load_config() -> AppConfig:
        return config

    def fake_configure_logging(cfg: AppConfig) -> None:
        assert cfg is config
        called["configured"] = True

    class FakeApp:
        def run_polling(self) -> None:
            called["ran"] = True

    def fake_build_application(cfg: AppConfig) -> FakeApp:
        assert cfg is config
        return FakeApp()

    monkeypatch.setattr("bot.main.load_config", fake_load_config)
    monkeypatch.setattr("bot.main.configure_logging", fake_configure_logging)
    monkeypatch.setattr("bot.main.build_application", fake_build_application)

    main()
    assert called == {"configured": True, "ran": True}

