"""GitHub trending retrieval via the gtrending library."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from gtrending import fetch_repos  # type: ignore[import-untyped]

README_BRANCHES = ("main", "master")
README_FILENAMES = ("README.md", "README.rst", "README.txt", "README")
README_TIMEOUT_SECONDS = 4
DESCRIPTION_MAX_LENGTH = 220


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


def _truncate_description(text: str, max_length: int = DESCRIPTION_MAX_LENGTH) -> str:
    """Trim a description to a compact sentence-like length."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned

    truncated = cleaned[: max_length + 1].rsplit(" ", maxsplit=1)[0].rstrip(".,;:")
    return f"{truncated}..."


def _strip_markdown_links(text: str) -> str:
    """Remove common inline Markdown link/image syntax while keeping readable text."""
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", text)
    return text


def _description_from_readme(readme: str) -> str | None:
    """Extract a short project summary from README text."""
    readme = re.sub(r"<!--.*?-->", "", readme, flags=re.DOTALL)
    readme = re.sub(r"```.*?```", "", readme, flags=re.DOTALL)
    readme = re.sub(r"<[^>]+>", " ", readme)

    lines: list[str] = []
    for raw_line in readme.splitlines():
        line = raw_line.strip()
        if not line:
            if lines:
                break
            continue
        if line.startswith(("#", "---", "===", "[!", "![", "<picture", "<img")):
            continue
        line = _strip_markdown_links(line)
        line = line.strip(" -*_`>|")
        if line:
            lines.append(line)

    if not lines:
        return None

    return _truncate_description(" ".join(lines))


def _guess_description(owner: str, repo: str) -> str:
    """Build a best-effort description when GitHub About and README are unavailable."""
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", repo)
    words = re.sub(r"[-_.]+", " ", words).strip()
    project_name = words or repo
    return _truncate_description(f"Project repository for {project_name} by {owner}.")


def _readme_summary(owner: str, repo: str) -> str | None:
    """Try to fetch and summarize a repository README from common raw URLs."""
    for branch in README_BRANCHES:
        for filename in README_FILENAMES:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
            try:
                with urlopen(url, timeout=README_TIMEOUT_SECONDS) as response:
                    readme = response.read(64_000).decode("utf-8", errors="ignore")
            except (HTTPError, URLError, TimeoutError):
                continue

            description = _description_from_readme(readme)
            if description:
                return description
    return None


def _fallback_description(owner: str, repo: str) -> str:
    """Return README-derived or guessed text for repos without a GitHub About field."""
    return _readme_summary(owner, repo) or _guess_description(owner, repo)


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

    url = str(item.get("url") or f"https://github.com/{owner}/{repo}").strip()
    stars = _to_int(item.get("stars"))
    return TrendingRepo(
        owner=owner,
        repo=repo,
        stars=stars,
        description=str(item.get("description") or "").strip(),
        url=url,
    )


async def fetch_top_repositories(
    since: str,
    top_n: int,
    language: str | None = None,
) -> list[TrendingRepo]:
    """Fetch and normalize top trending repositories from gtrending."""
    if top_n < 1:
        raise ValueError("top_n must be at least 1")

    def _fetch() -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], fetch_repos(since=since, language=language))

    raw_items = await asyncio.to_thread(_fetch)
    normalized: list[TrendingRepo] = []
    for item in raw_items:
        try:
            repo = _normalize(item)
        except ValueError:
            continue
        if not repo.description:
            description = await asyncio.to_thread(_fallback_description, repo.owner, repo.repo)
            repo = replace(repo, description=description)
        normalized.append(repo)
        if len(normalized) >= top_n:
            break
    if len(normalized) < top_n:
        raise RuntimeError(f"Incomplete trending snapshot: {len(normalized)}/{top_n}")
    return normalized
