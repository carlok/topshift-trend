"""GitHub trending retrieval via the gtrending library."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast

from gtrending import fetch_repos  # type: ignore[import-untyped]


@dataclass(frozen=True)
class TrendingRepo:
    """Normalized representation of a trending repository."""

    owner: str
    repo: str
    stars: int
    description: str
    url: str

    @property
    def key(self) -> str:
        """Case-insensitive identifier used for diffing."""
        return f"{self.owner}/{self.repo}".lower()


def _to_int(value: Any) -> int:
    """Convert value to int, returning zero for malformed values."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        return int(cleaned) if cleaned.isdigit() else 0
    return 0


def _normalize(item: dict[str, Any]) -> TrendingRepo:
    """Normalize a gtrending item into a TrendingRepo object."""
    fullname = str(item.get("fullname") or "").strip()
    author = str(item.get("author") or "").strip()
    name = str(item.get("name") or "").strip()

    if "/" in fullname:
        owner, repo = fullname.split("/", maxsplit=1)
    else:
        owner, repo = author, name

    owner = owner.strip()
    repo = repo.strip()

    if not owner or not repo:
        raise ValueError("Unable to derive owner/repo from trending item")

    description = str(item.get("description") or "").strip()
    url = str(item.get("url") or f"https://github.com/{owner}/{repo}").strip()
    stars = _to_int(item.get("stars"))
    return TrendingRepo(
        owner=owner,
        repo=repo,
        stars=stars,
        description=description,
        url=url,
    )


async def fetch_top_repositories(
    since: str,
    top_n: int,
    language: str | None = None,
) -> list[TrendingRepo]:
    """Fetch and normalize top trending repositories from gtrending."""

    def _fetch() -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], fetch_repos(since=since, language=language))

    raw_items = await asyncio.to_thread(_fetch)
    normalized: list[TrendingRepo] = []
    for item in raw_items:
        try:
            normalized.append(_normalize(item))
        except ValueError:
            continue
        if len(normalized) >= top_n:
            break
    return normalized

