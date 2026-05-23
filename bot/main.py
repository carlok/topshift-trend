"""Application entry point: Telegram handlers and scheduled checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.config import AppConfig, load_config
from bot.notifier import format_top_snapshot, notify_subscribers, send_to_chat
from bot.scraper import TrendingRepo, fetch_top_repositories
from bot.store import JsonStore

LOGGER = logging.getLogger(__name__)


def command_help_text() -> str:
    """Return the command reference shown to users."""
    return (
        "Available commands:\n"
        "/start - subscribe and get the current top list\n"
        "/stop - unsubscribe from notifications\n"
        "/check - run an immediate check (caller only)\n"
        "/top - show current top list (caller only)\n"
        "/help - show this command list"
    )


@dataclass(frozen=True)
class CheckResult:
    """Check result details used for logging and command responses."""

    current: list[TrendingRepo]
    new_entries: list[TrendingRepo]


class TopShiftRuntime:
    """Runtime service coordinating scraping, diffing, and notifications."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.store = JsonStore(config.data_dir)
        self.scheduler: AsyncIOScheduler | None = None

    async def run_check(self, *, commit: bool = False) -> CheckResult:
        """Fetch top repositories and compute diff, optionally persisting the baseline."""
        previous_state = self.store.load_state()
        current = await fetch_top_repositories(
            since=self.config.resolved_since(),
            top_n=self.config.top_n,
            language=self.config.resolved_language(),
        )
        new_entries = self.store.new_entries(previous_state, current)
        if commit:
            self.store.save_state(current)
        return CheckResult(current=current, new_entries=new_entries)


def configure_logging(config: AppConfig) -> None:
    """Configure application logging format and level."""
    logging.basicConfig(
        level=config.normalized_log_level(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # Suppress per-request transport logs from polling internals.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_runtime(context: ContextTypes.DEFAULT_TYPE) -> TopShiftRuntime:
    """Return runtime object from application bot data."""
    runtime = context.application.bot_data.get("runtime")
    if not isinstance(runtime, TopShiftRuntime):
        raise RuntimeError("Runtime is not configured")
    return runtime


async def run_scheduled_check(application: Any) -> None:
    """Run one scheduled check and notify all subscribers for new entries."""
    runtime = application.bot_data["runtime"]
    assert isinstance(runtime, TopShiftRuntime)
    LOGGER.info("Scheduled check started")
    try:
        result = await runtime.run_check()
        subscribers = runtime.store.load_subscribers()
        sent = 0
        if result.new_entries:
            notification_result = await notify_subscribers(
                application.bot,
                subscribers,
                result.new_entries,
            )
            sent = notification_result.sent_count
            for chat_id in notification_result.dropped_subscribers:
                runtime.store.remove_subscriber(chat_id)
        runtime.store.save_state(result.current)
        LOGGER.info(
            "Scheduled check finished | current=%s | new=%s | notifications=%s",
            len(result.current),
            len(result.new_entries),
            sent,
        )
    except Exception:
        LOGGER.exception("Scheduled check failed")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Subscribe the user and send full snapshot for first-time subscribers."""
    if update.effective_chat is None:
        return

    runtime = get_runtime(context)
    chat_id = update.effective_chat.id
    is_new = runtime.store.add_subscriber(chat_id)
    await send_to_chat(context.bot, chat_id, command_help_text())

    if is_new:
        await send_to_chat(
            context.bot,
            chat_id,
            "Subscribed to TopShift notifications.",
        )
        state = runtime.store.load_state()
        if state and state.get("top"):
            repos = [
                TrendingRepo(
                    owner=item["owner"],
                    repo=item["repo"],
                    stars=int(item.get("stars", 0)),
                    description=str(item.get("description", "")),
                    url=str(item.get("url", "")),
                )
                for item in state["top"][: runtime.config.top_n]
            ]
        else:
            check = await runtime.run_check(commit=True)
            repos = check.current
        await send_to_chat(context.bot, chat_id, format_top_snapshot(repos))
    else:
        await send_to_chat(context.bot, chat_id, "You are already subscribed.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available command list."""
    if update.effective_chat is None:
        return
    await send_to_chat(context.bot, update.effective_chat.id, command_help_text())


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unsubscribe the calling chat."""
    if update.effective_chat is None:
        return
    runtime = get_runtime(context)
    removed = runtime.store.remove_subscriber(update.effective_chat.id)
    message = "Unsubscribed from TopShift notifications." if removed else "You were not subscribed."
    await send_to_chat(context.bot, update.effective_chat.id, message)


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch and send the current top list to the caller only."""
    if update.effective_chat is None:
        return
    runtime = get_runtime(context)
    try:
        repos = await fetch_top_repositories(
            since=runtime.config.resolved_since(),
            top_n=runtime.config.top_n,
            language=runtime.config.resolved_language(),
        )
        await send_to_chat(context.bot, update.effective_chat.id, format_top_snapshot(repos))
    except Exception:
        LOGGER.exception("Manual /top failed")
        await send_to_chat(
            context.bot,
            update.effective_chat.id,
            "Failed to fetch current top list.",
        )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run one immediate check and report only to the caller."""
    if update.effective_chat is None:
        return
    runtime = get_runtime(context)
    chat_id = update.effective_chat.id
    try:
        result = await runtime.run_check()
        if result.new_entries:
            entry_label = "entry" if len(result.new_entries) == 1 else "entries"
            summary = [
                f"Found {len(result.new_entries)} new {entry_label}:"
            ]
            summary.extend([f"- {repo.owner}/{repo.repo}" for repo in result.new_entries])
            await send_to_chat(context.bot, chat_id, "\n".join(summary))
        else:
            await send_to_chat(context.bot, chat_id, "No new repositories entered the top list.")
    except Exception:
        LOGGER.exception("Manual /check failed")
        await send_to_chat(context.bot, chat_id, "Check failed. See logs for details.")


async def post_init(application: Any) -> None:
    """Start APScheduler after Telegram application is initialized."""
    runtime = application.bot_data["runtime"]
    assert isinstance(runtime, TopShiftRuntime)
    scheduler = AsyncIOScheduler()
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Subscribe and receive the current top list"),
            BotCommand("stop", "Unsubscribe from notifications"),
            BotCommand("check", "Run an immediate check"),
            BotCommand("top", "Show the current top list"),
            BotCommand("help", "Show available commands"),
        ]
    )
    scheduler.add_job(
        run_scheduled_check,
        CronTrigger.from_crontab(runtime.config.check_schedule_cron),
        kwargs={"application": application},
        id="scheduled-trending-check",
        replace_existing=True,
    )
    scheduler.start()
    runtime.scheduler = scheduler
    LOGGER.info("Scheduler started with cron '%s'", runtime.config.check_schedule_cron)


async def post_shutdown(application: Any) -> None:
    """Stop APScheduler when application shuts down."""
    runtime = application.bot_data.get("runtime")
    if isinstance(runtime, TopShiftRuntime) and runtime.scheduler is not None:
        runtime.scheduler.shutdown(wait=False)
        LOGGER.info("Scheduler stopped")


def build_application(config: AppConfig) -> Any:
    """Create and configure the Telegram application instance."""
    runtime = TopShiftRuntime(config)
    application = (
        Application.builder()
        .token(config.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["runtime"] = runtime
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("stop", cmd_stop))
    application.add_handler(CommandHandler("check", cmd_check))
    application.add_handler(CommandHandler("top", cmd_top))
    application.add_handler(CommandHandler("help", cmd_help))
    return application


def main() -> None:
    """Run the bot process."""
    config = load_config()
    configure_logging(config)
    LOGGER.info("TopShift bot starting")
    app = build_application(config)
    app.run_polling()


if __name__ == "__main__":
    main()
