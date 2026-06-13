"""Tests for scraper normalization logic."""

from __future__ import annotations

from threading import Barrier
from urllib.error import URLError

import pytest

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


async def test_fetch_top_repositories_rejects_incomplete_snapshot(monkeypatch) -> None:
    """Incomplete snapshots should fail instead of becoming the new baseline."""

    def fake_fetch_repos(*, since: str, language: str | None):
        return [
            {
                "fullname": "owner1/repo1",
                "stars": "1,234",
                "description": "Repo one",
                "url": "https://github.com/owner1/repo1",
            }
        ]

    monkeypatch.setattr("bot.scraper.fetch_repos", fake_fetch_repos)

    with pytest.raises(RuntimeError, match="Incomplete trending snapshot: 1/2"):
        await fetch_top_repositories(since="monthly", top_n=2, language=None)


async def test_fetch_top_repositories_rejects_non_positive_top_n(monkeypatch) -> None:
    """Invalid top_n values should fail before fetching or returning a stray item."""

    def fake_fetch_repos(*, since: str, language: str | None):
        raise AssertionError("fetch should not run for invalid top_n")

    monkeypatch.setattr("bot.scraper.fetch_repos", fake_fetch_repos)

    with pytest.raises(ValueError, match="top_n must be at least 1"):
        await fetch_top_repositories(since="monthly", top_n=0, language=None)


async def test_fetch_top_repositories_uses_readme_when_description_missing(monkeypatch) -> None:
    """Missing About text should fall back to a short README-derived summary."""

    def fake_fetch_repos(*, since: str, language: str | None):
        return [
            {
                "fullname": "owner/readme-repo",
                "stars": 10,
                "description": "",
                "url": "https://github.com/owner/readme-repo",
            }
        ]

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return (
                b"# readme-repo\n\n"
                b"A small tool that turns project READMEs into useful summaries."
            )

    monkeypatch.setattr("bot.scraper.fetch_repos", fake_fetch_repos)
    monkeypatch.setattr("bot.scraper.urlopen", lambda *args, **kwargs: FakeResponse())

    repos = await fetch_top_repositories(since="monthly", top_n=1, language=None)

    assert repos[0].description == "A small tool that turns project READMEs into useful summaries."


async def test_fetch_top_repositories_enriches_missing_descriptions_concurrently(
    monkeypatch,
) -> None:
    """Missing descriptions should be enriched concurrently while preserving result order."""

    def fake_fetch_repos(*, since: str, language: str | None):
        return [
            {
                "fullname": "owner/first",
                "stars": 10,
                "description": "",
                "url": "https://github.com/owner/first",
            },
            {
                "fullname": "owner/second",
                "stars": 20,
                "description": "",
                "url": "https://github.com/owner/second",
            },
        ]

    barrier = Barrier(2)

    def fake_fallback_description(owner: str, repo: str) -> str:
        barrier.wait(timeout=1)
        return f"{owner}/{repo} summary"

    monkeypatch.setattr("bot.scraper.fetch_repos", fake_fetch_repos)
    monkeypatch.setattr("bot.scraper._fallback_description", fake_fallback_description)

    repos = await fetch_top_repositories(since="monthly", top_n=2, language=None)

    assert [repo.repo for repo in repos] == ["first", "second"]
    assert [repo.description for repo in repos] == [
        "owner/first summary",
        "owner/second summary",
    ]


async def test_fetch_top_repositories_guesses_when_readme_unavailable(monkeypatch) -> None:
    """Missing About and README text should still produce a useful best-effort description."""

    def fake_fetch_repos(*, since: str, language: str | None):
        return [
            {
                "fullname": "owner/missing-about",
                "stars": 10,
                "description": "",
                "url": "https://github.com/owner/missing-about",
            }
        ]

    def fake_urlopen(*args: object, **kwargs: object):
        raise URLError("not found")

    monkeypatch.setattr("bot.scraper.fetch_repos", fake_fetch_repos)
    monkeypatch.setattr("bot.scraper.urlopen", fake_urlopen)

    repos = await fetch_top_repositories(since="monthly", top_n=1, language=None)

    assert repos[0].description == "Project repository for missing about by owner."
