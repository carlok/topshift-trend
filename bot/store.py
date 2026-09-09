"""JSON-backed persistence for top repositories and subscribers."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from bot.scraper import TrendingRepo

LOGGER = logging.getLogger(__name__)


class JsonStore:
    """Persistence helper for state and subscriber records."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.state_path = data_dir / "state.json"
        self.subscribers_path = data_dir / "subscribers.json"
        self.notification_history_path = data_dir / "notification_history.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict[str, Any] | None:
        """Load persisted state if present."""
        if not self.state_path.exists():
            return None
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.exception("Failed to decode state file at %s", self.state_path)
            return None
        if not isinstance(payload, dict):
            LOGGER.warning("Invalid state payload at %s", self.state_path)
            return None
        return cast(dict[str, Any], payload)

    def save_state(self, repos: list[TrendingRepo]) -> None:
        """Persist normalized repositories as the latest baseline."""
        payload = {
            "checked_at": datetime.now(UTC).isoformat(),
            "top": [asdict(repo) for repo in repos],
        }
        self._atomic_write(self.state_path, payload)

    def load_subscribers(self) -> set[int]:
        """Load subscribers set from disk."""
        if not self.subscribers_path.exists():
            return set()
        try:
            payload = json.loads(self.subscribers_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.exception("Failed to decode subscribers file at %s", self.subscribers_path)
            return set()
        if not isinstance(payload, dict):
            LOGGER.warning("Invalid subscribers payload at %s", self.subscribers_path)
            return set()
        chat_ids = payload.get("chat_ids", [])
        if not isinstance(chat_ids, list):
            LOGGER.warning("Invalid subscribers payload at %s", self.subscribers_path)
            return set()

        subscribers: set[int] = set()
        for chat_id in chat_ids:
            try:
                subscribers.add(int(chat_id))
            except (TypeError, ValueError):
                LOGGER.warning("Skipping invalid subscriber chat_id=%r", chat_id)
        return subscribers

    def save_subscribers(self, subscribers: set[int]) -> None:
        """Persist subscribers set to disk."""
        payload = {"chat_ids": sorted(subscribers)}
        self._atomic_write(self.subscribers_path, payload)

    def recent_notification_keys(self, cooldown_days: int) -> set[str]:
        """Return repository keys notified within the configured cooldown."""
        if cooldown_days <= 0 or not self.notification_history_path.exists():
            return set()

        try:
            payload = json.loads(self.notification_history_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.exception(
                "Failed to decode notification history at %s", self.notification_history_path
            )
            return set()
        if not isinstance(payload, dict):
            LOGGER.warning("Invalid notification history at %s", self.notification_history_path)
            return set()

        sent_at = payload.get("sent_at", {})
        if not isinstance(sent_at, dict):
            LOGGER.warning("Invalid notification history at %s", self.notification_history_path)
            return set()

        cutoff = datetime.now(UTC).timestamp() - cooldown_days * 24 * 60 * 60
        recent_keys: set[str] = set()
        for key, value in sent_at.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            try:
                notified_at = datetime.fromisoformat(value)
            except ValueError:
                continue
            if notified_at.tzinfo is None:
                notified_at = notified_at.replace(tzinfo=UTC)
            if notified_at.timestamp() >= cutoff:
                recent_keys.add(key.lower())
        return recent_keys

    def record_notifications(self, repos: list[TrendingRepo]) -> None:
        """Record repositories that were successfully sent to at least one subscriber."""
        sent_at: dict[str, str] = {}
        if self.notification_history_path.exists():
            try:
                payload = json.loads(self.notification_history_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                LOGGER.exception(
                    "Failed to decode notification history at %s", self.notification_history_path
                )
                payload = {}
            if isinstance(payload, dict) and isinstance(payload.get("sent_at"), dict):
                sent_at = {
                    key: value
                    for key, value in payload["sent_at"].items()
                    if isinstance(key, str) and isinstance(value, str)
                }

        now = datetime.now(UTC).isoformat()
        for repo in repos:
            sent_at[repo.key] = now
        self._atomic_write(self.notification_history_path, {"sent_at": sent_at})

    def add_subscriber(self, chat_id: int) -> bool:
        """Add subscriber and return True only when newly added."""
        subscribers = self.load_subscribers()
        before = len(subscribers)
        subscribers.add(chat_id)
        self.save_subscribers(subscribers)
        return len(subscribers) > before

    def remove_subscriber(self, chat_id: int) -> bool:
        """Remove subscriber and return True only when removed."""
        subscribers = self.load_subscribers()
        if chat_id not in subscribers:
            return False
        subscribers.remove(chat_id)
        self.save_subscribers(subscribers)
        return True

    @staticmethod
    def new_entries(
        previous_state: dict[str, Any] | None,
        current: list[TrendingRepo],
    ) -> list[TrendingRepo]:
        """Return repositories that newly entered the top list."""
        if not previous_state or "top" not in previous_state:
            return []

        previous_keys: set[str] = set()
        for item in previous_state.get("top", []):
            if not isinstance(item, dict):
                LOGGER.warning("Skipping malformed state entry during diff: %r", item)
                continue

            owner = str(item.get("owner", "")).strip()
            repo = str(item.get("repo", "")).strip()
            if owner and repo:
                previous_keys.add(f"{owner}/{repo}".lower())

        return [repo for repo in current if repo.key not in previous_keys]

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        """Safely write JSON payload via temp file swap."""
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)
