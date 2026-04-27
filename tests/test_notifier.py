"""Tests for notification formatting and dispatch."""

from __future__ import annotations

from bot.notifier import format_new_entry_message, notify_subscribers
from bot.scraper import TrendingRepo


def test_format_new_entry_message() -> None:
    """Message formatter should include expected payload fields."""
    repo = TrendingRepo(
        owner="owner",
        repo="repo",
        stars=12345,
        description="One line.",
        url="https://github.com/owner/repo",
    )
    message = format_new_entry_message(repo)
    assert "🚀 New in GitHub Top 10 Trending" in message
    assert "owner/repo" in message
    assert "★ 12,345 stars" in message
    assert "\"One line.\"" in message
    assert "https://github.com/owner/repo" in message


async def test_notify_subscribers_dispatches(monkeypatch) -> None:
    """Notifier should call bot.send_message for each chat and entry."""
    sent: list[tuple[int, str]] = []

    class FakeBot:
        async def send_message(
            self,
            chat_id: int,
            text: str,
            disable_web_page_preview: bool = False,
        ):
            sent.append((chat_id, text))

    repo = TrendingRepo(
        owner="owner",
        repo="repo",
        stars=123,
        description="desc",
        url="https://github.com/owner/repo",
    )

    bot = FakeBot()
    count = await notify_subscribers(bot=bot, subscribers={1, 2}, new_entries=[repo])
    assert count == 2
    assert len(sent) == 2
    assert all("owner/repo" in text for _, text in sent)

