"""Tests for notification formatting and dispatch."""

from __future__ import annotations

from telegram.error import Forbidden

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
    result = await notify_subscribers(bot=bot, subscribers={1, 2}, new_entries=[repo])
    assert result.sent_count == 2
    assert result.dropped_subscribers == set()
    assert len(sent) == 2
    assert all("owner/repo" in text for _, text in sent)


async def test_notify_subscribers_drops_unreachable_chat() -> None:
    """Permanent Telegram failures should mark the chat for removal."""

    class FakeBot:
        async def send_message(
            self,
            chat_id: int,
            text: str,
            disable_web_page_preview: bool = False,
        ):
            if chat_id == 2:
                raise Forbidden("bot was blocked by the user")

    repo = TrendingRepo(
        owner="owner",
        repo="repo",
        stars=123,
        description="desc",
        url="https://github.com/owner/repo",
    )

    result = await notify_subscribers(bot=FakeBot(), subscribers={1, 2}, new_entries=[repo])

    assert result.sent_count == 1
    assert result.dropped_subscribers == {2}


async def test_notify_subscribers_reports_transient_failure() -> None:
    """Unexpected send failures should be reported without raising."""

    class FakeBot:
        async def send_message(
            self,
            chat_id: int,
            text: str,
            disable_web_page_preview: bool = False,
        ):
            raise RuntimeError("network")

    repo = TrendingRepo(
        owner="owner",
        repo="repo",
        stars=123,
        description="desc",
        url="https://github.com/owner/repo",
    )

    result = await notify_subscribers(bot=FakeBot(), subscribers={1}, new_entries=[repo])
    assert result.sent_count == 0
    assert result.transient_failed_subscribers == {1}
    assert result.delivered_by_chat == {}


async def test_notify_subscribers_skips_keys_already_delivered() -> None:
    """Per-chat skip keys should prevent resending a delivered repository."""
    sent: list[str] = []

    class FakeBot:
        async def send_message(
            self,
            chat_id: int,
            text: str,
            disable_web_page_preview: bool = False,
        ):
            sent.append(text)

    first = TrendingRepo(
        owner="first",
        repo="repo",
        stars=1,
        description="d",
        url="https://github.com/first/repo",
    )
    second = TrendingRepo(
        owner="second",
        repo="repo",
        stars=1,
        description="d",
        url="https://github.com/second/repo",
    )

    result = await notify_subscribers(
        bot=FakeBot(),
        subscribers={1},
        new_entries=[first, second],
        skip_keys_by_chat={1: {"first/repo"}},
    )

    assert result.sent_count == 1
    assert any("second/repo" in text for text in sent)
    assert not any("first/repo" in text for text in sent)
