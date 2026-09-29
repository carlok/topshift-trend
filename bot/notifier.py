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
    delivered_by_chat: dict[int, tuple[TrendingRepo, ...]]
    transient_failed_subscribers: set[int]


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
    *,
    skip_keys_by_chat: dict[int, set[str]] | None = None,
) -> NotificationResult:
    """Dispatch new entry notifications to all reachable subscribers.

    Transient send failures are returned in the result instead of raising, so
    callers can persist successful deliveries before retrying the rest.
    """
    sent_count = 0
    dropped_subscribers: set[int] = set()
    transient_failed_subscribers: set[int] = set()
    delivered_by_chat: dict[int, list[TrendingRepo]] = {}
    skip_keys_by_chat = skip_keys_by_chat or {}

    for chat_id in subscribers:
        skip_keys = skip_keys_by_chat.get(chat_id, set())
        for repo in new_entries:
            if repo.key in skip_keys:
                continue
            try:
                await send_to_chat(bot, chat_id, format_new_entry_message(repo))
                sent_count += 1
                delivered_by_chat.setdefault(chat_id, []).append(repo)
                LOGGER.info("Notified chat_id=%s for %s/%s", chat_id, repo.owner, repo.repo)
            except (BadRequest, Forbidden):
                dropped_subscribers.add(chat_id)
                LOGGER.exception("Dropping unreachable subscriber chat_id=%s", chat_id)
                break
            except Exception:
                transient_failed_subscribers.add(chat_id)
                LOGGER.exception("Failed to notify chat_id=%s", chat_id)
                break

    return NotificationResult(
        sent_count=sent_count,
        dropped_subscribers=dropped_subscribers,
        delivered_by_chat={
            chat_id: tuple(repos) for chat_id, repos in delivered_by_chat.items()
        },
        transient_failed_subscribers=transient_failed_subscribers,
    )
