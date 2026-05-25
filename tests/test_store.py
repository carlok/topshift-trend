"""Tests for JSON store behavior and diff logic."""

from __future__ import annotations

from pathlib import Path

from bot.scraper import TrendingRepo
from bot.store import JsonStore


def _repo(owner: str, repo: str) -> TrendingRepo:
    return TrendingRepo(
        owner=owner,
        repo=repo,
        stars=100,
        description="desc",
        url=f"https://github.com/{owner}/{repo}",
    )


def test_new_entries_first_run_returns_none(tmp_path: Path) -> None:
    """When state is missing, bootstrap without treating all repos as new."""
    current = [_repo("one", "alpha"), _repo("two", "beta")]
    assert JsonStore.new_entries(previous_state=None, current=current) == []


def test_new_entries_filters_existing_case_insensitive(tmp_path: Path) -> None:
    """Diff should compare owner/repo in case-insensitive mode."""
    previous = {
        "checked_at": "2026-01-01T00:00:00+00:00",
        "top": [{"owner": "One", "repo": "Alpha"}],
    }
    current = [_repo("one", "alpha"), _repo("two", "beta")]
    diff = JsonStore.new_entries(previous_state=previous, current=current)
    assert [item.key for item in diff] == ["two/beta"]


def test_subscriber_add_remove_roundtrip(tmp_path: Path) -> None:
    """Adding and removing subscribers should persist correctly."""
    store = JsonStore(tmp_path)
    assert store.add_subscriber(123) is True
    assert store.add_subscriber(123) is False
    assert store.load_subscribers() == {123}
    assert store.remove_subscriber(123) is True
    assert store.remove_subscriber(123) is False


def test_corrupted_json_loads_as_empty(tmp_path: Path) -> None:
    """Corrupted JSON should not crash state or subscriber loads."""
    store = JsonStore(tmp_path)
    store.state_path.write_text("{", encoding="utf-8")
    store.subscribers_path.write_text("{", encoding="utf-8")

    assert store.load_state() is None
    assert store.load_subscribers() == set()


def test_malformed_subscriber_ids_are_ignored(tmp_path: Path) -> None:
    """Malformed subscriber records should not prevent valid subscribers from loading."""
    store = JsonStore(tmp_path)
    store.subscribers_path.write_text(
        '{"chat_ids": [123, "456", "bad", null]}',
        encoding="utf-8",
    )

    assert store.load_subscribers() == {123, 456}
