# TopShift implementation notes

## Trending source decision

This project intentionally uses [`gtrending`](https://github.com/hedyhli/gtrending)
as the only trending data source.

Why:

- It directly wraps the public GitHub Trending page and returns structured repository data.
- It avoids implementing first-party scraping logic inside this repository.
- It provides the fields needed by this bot (`fullname`, `stars`, `description`, `url`).

Trade-offs:

- `gtrending` is not an official GitHub API.
- Upstream GitHub markup changes can break `gtrending`.
- The latest tagged release is older, so version is pinned in `pyproject.toml`.

## Known limitations

- If GitHub Trending format changes upstream, fetch calls may fail until `gtrending` is updated.
- `/check` updates the saved baseline state after each run.
- Telegram messages are plain text and can be split if top list content grows.

