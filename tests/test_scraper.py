"""Tests for scraper normalization logic."""

from __future__ import annotations

from bot.scraper import fetch_top_repositories


async def test_fetch_top_repositories_normalizes_and_limits(monkeypatch) -> None:
    """Scraper should normalize fields and respect top_n limits."""

    def fake_fetch_repos(*, since: str, language: str | None):
        assert since == "monthly"
        assert language == "python"
        return [
            {
                "fullname": "owner1/repo1",
                "stars": "1,234",
                "description": "Repo one",
                "url": "https://github.com/owner1/repo1",
            },
            {
                "author": "owner2",
                "name": "repo2",
                "stars": 88,
                "description": "Repo two",
                "url": "https://github.com/owner2/repo2",
            },
            {
                "fullname": "",
                "author": "",
                "name": "",
                "stars": 0,
            },
        ]

    monkeypatch.setattr("bot.scraper.fetch_repos", fake_fetch_repos)
    repos = await fetch_top_repositories(since="monthly", top_n=2, language="python")

    assert len(repos) == 2
    assert repos[0].owner == "owner1"
    assert repos[0].repo == "repo1"
    assert repos[0].stars == 1234
    assert repos[1].owner == "owner2"
    assert repos[1].repo == "repo2"

