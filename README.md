# topshift-trend

[Try the bot on Telegram](https://t.me/ghTopShift_bot).

Telegram bot that tracks **new entries** in GitHub monthly trending top repositories
and notifies subscribed chats.

## What it does

- Runs on an internal APScheduler cron (no host cron dependency).
- Fetches trending repositories through [`gtrending`](https://github.com/hedyhli/gtrending).
- Compares current top list with the previously saved state.
- Sends notifications only for repositories that **entered** the top list since the last check.

## Commands

- `/start` subscribe this chat; first subscription receives full current top list.
- `/stop` unsubscribe this chat.
- `/check` run an immediate check and report to caller only without advancing the saved baseline.
- `/top` fetch and show current top list to caller only.

## Configuration

Copy `.env.example` to `.env` and fill values:

```bash
cp .env.example .env
```

Required:

- `TELEGRAM_BOT_TOKEN`: bot token from BotFather.

Optional defaults are already set:

- `CHECK_SCHEDULE_CRON=0 8 * * *`
- `TRENDING_URL=https://github.com/trending?since=monthly`
- `TOP_N=10`
- `DATA_DIR=/data`
- `LOG_LEVEL=INFO`
- `PUID=1000`
- `PGID=1000`

## Local run with Podman

```bash
podman compose up -d --build
podman compose logs -f
```

Data is persisted to `./data` on the host and mounted to `/data` in the container.

On macOS/Linux, set `PUID`/`PGID` in `.env` to your local user IDs so the
container user can write mounted files:

```bash
echo "PUID=$(id -u)" >> .env
echo "PGID=$(id -g)" >> .env
```

If you already have permission issues, also run:

```bash
chmod -R u+rwX data
```

## Quality checks

The project uses:

- `ruff` for linting
- `mypy` for type checks
- `pytest` + `pytest-cov` with 80% minimum coverage

Run all checks inside Podman:

```bash
podman run --rm -v "$PWD:/app" -w /app docker.io/library/python:3.12-slim \
  sh -lc "pip install --no-cache-dir -e '.[dev]' && ruff check . && mypy bot && pytest"
```

## Make targets

- `make test` run pytest with coverage.
- `make lint` run ruff and mypy.
- `make up` run `podman compose up -d`.
- `make logs` follow compose logs.
