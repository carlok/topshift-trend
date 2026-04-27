FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY pyproject.toml README.md /app/
COPY bot /app/bot

RUN pip install --no-cache-dir .

RUN mkdir -p /data && chown -R appuser:appuser /app /data

USER appuser

CMD ["python", "-m", "bot.main"]

