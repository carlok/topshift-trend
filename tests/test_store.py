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


def test_new_entries_first_run_returns_all(tmp_path: Path) -> None:
    """When state is missing, every current repo is considered new."""
    current = [_repo("one", "alpha"), _repo("two", "beta")]
    assert JsonStore.new_entries(previous_state=None, current=current) == current


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

