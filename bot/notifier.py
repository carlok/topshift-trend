"""Telegram message formatting and delivery helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from telegram import Bot
from telegram.error import BadRequest, Forbidden

from bot.scraper import TrendingRepo

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationResult:
    """Summary of a notification dispatch run."""

    sent_count: int
    dropped_subscribers: set[int]


def format_new_entry_message(repo: TrendingRepo) -> str:
    """Build the notification message for newly entered repositories."""
    description = repo.description or "No description."
    return (
        "🚀 New in GitHub Top 10 Trending\n\n"
        f"{repo.owner}/{repo.repo}\n"
        f"★ {repo.stars:,} stars\n"
        f"\"{description}\"\n\n"
        f"{repo.url}"
    )


def format_top_snapshot(repos: list[TrendingRepo]) -> str:
    """Build a compact full top-N snapshot for manual commands."""
    if not repos:
        return "No repositories found in the current trending snapshot."

    lines: list[str] = ["📈 Current GitHub Trending Top list\n"]
    for index, repo in enumerate(repos, start=1):
        description = repo.description or "No description."
        lines.extend(
            [
                f"{index}. {repo.owner}/{repo.repo}",
                f"   ★ {repo.stars:,}",
                f"   {description}",
                f"   {repo.url}",
                "",
            ]
        )
    return "\n".join(lines).strip()


async def send_to_chat(bot: Bot, chat_id: int, text: str) -> None:
    """Send a message to one chat with markdown disabled."""
    await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=False)


async def notify_subscribers(
    bot: Bot,
    subscribers: set[int],
    new_entries: list[TrendingRepo],
) -> NotificationResult:
    """Dispatch new entry notifications to all reachable subscribers."""
    sent_count = 0
    dropped_subscribers: set[int] = set()
    transient_failures: list[int] = []
    for chat_id in subscribers:
        for repo in new_entries:
            try:
                await send_to_chat(bot, chat_id, format_new_entry_message(repo))
                sent_count += 1
                LOGGER.info("Notified chat_id=%s for %s/%s", chat_id, repo.owner, repo.repo)
            except (BadRequest, Forbidden):
                dropped_subscribers.add(chat_id)
                LOGGER.exception("Dropping unreachable subscriber chat_id=%s", chat_id)
                break
            except Exception:
                transient_failures.append(chat_id)
                LOGGER.exception("Failed to notify chat_id=%s", chat_id)

    if transient_failures:
        unique_failures = sorted(set(transient_failures))
        raise RuntimeError(f"Transient notification failures for chats: {unique_failures}")

    return NotificationResult(sent_count=sent_count, dropped_subscribers=dropped_subscribers)
