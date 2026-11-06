# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm AS builder

# gcr.io/distroless/python3-debian12 ships Debian's Python 3.11 at
# /usr/bin/python3. Expose the builder's 3.11 at that same path and create the
# venv through it explicitly, so the venv's python symlink and pyvenv.cfg
# `home` point to /usr/bin (plain `python3` would resolve to /usr/local/bin,
# which does not exist in the runtime image).
RUN ln -sf /usr/local/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/local/bin/python3.11 /usr/bin/python3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY bot ./bot

RUN /usr/bin/python3 -m venv /build/.venv \
    && /build/.venv/bin/pip install --no-cache-dir . \
    && /build/.venv/bin/pip install --no-cache-dir --upgrade pip==26.1.2 \
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
