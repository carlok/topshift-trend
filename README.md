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
- `NOTIFICATION_COOLDOWN_DAYS=30`
- `DATA_DIR=/data`
- `LOG_LEVEL=INFO`

## Local run with Podman

```bash
podman compose up -d --build
podman compose logs -f
```

Data is persisted to `./data` on the host and mounted to `/data` in the container.

The production image is [Distroless](https://github.com/GoogleContainerTools/distroless) (`gcr.io/distroless/python3-debian12:nonroot`): no shell, package manager, or extra utilities. The bot starts with `python -m bot.main` only. [Docker Hardened Images](https://dhi.io/) publish Distroless-compatible Python bases when your registry provides them without extra authentication; this project uses the public Google image so anonymous pulls work without registry login.

### Data directory ownership

The container runs as the Distroless `nonroot` user (UID/GID **65532**); compose
does not override it. A bind-mounted `./data` must therefore be owned by 65532
inside the container's user namespace, or the bot cannot write its state files.

Rootless Podman (host UID is mapped to container root, so use `unshare`):

```bash
mkdir -p data
podman unshare chown -R 65532:65532 data
```

Rootful Docker / Podman:

```bash
sudo chown -R 65532:65532 data
```

To delete files under `data` later with rootless Podman, use
`podman unshare rm -rf data/<file>`.

### Inspecting the production container

Distroless images have no shell, so `podman exec … sh` does not work. Inspect
from the host instead:

```bash
podman compose logs -f                      # or: podman logs -f <container>
podman ps                                   # status, restarts
podman inspect <container>                  # config, mounts, user, exit code
podman cp <container>:/data ./data-snapshot # copy files out of the container
podman unshare ls -ln data                  # bind-mount ownership as seen by the container
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
