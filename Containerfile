# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm AS builder

# gcr.io/distroless/python3-debian12 ships Debian's Python 3.11. Build the
# production venv against the same interpreter path (/usr/bin/python3) that
# exists in that runtime image.
RUN ln -sf /usr/local/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/local/bin/python3.11 /usr/bin/python3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY bot ./bot

RUN python3 -m venv /build/.venv \
    && /build/.venv/bin/pip install --no-cache-dir . \
    && chmod -R a+rX /build

FROM python:3.11-slim-bookworm AS runtime-prep

RUN mkdir -p /data && chown 65532:65532 /data

# Public Distroless Python on Debian 12 (no extra registry auth in CI).
# Docker Hardened Images publish a drop-in alternative when your registry
# provides them without authentication.
FROM gcr.io/distroless/python3-debian12:nonroot AS runtime

COPY --from=runtime-prep --chown=65532:65532 /data /data
COPY --from=builder --chown=65532:65532 /build/.venv /app/.venv

ENV PYTHONUNBUFFERED=1

WORKDIR /app

ENTRYPOINT ["/app/.venv/bin/python3", "-m", "bot.main"]
