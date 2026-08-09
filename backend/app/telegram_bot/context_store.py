"""Local, file-based state for the long-polling bot: which Telegram update
was last processed (so getUpdates doesn't redeliver it), the numbered
listing shown by the last /tareas so /resumen <n> can resolve it, and
which assignment the free-form chat is currently "focused" on.

SQLite (stdlib, no new dependency) rather than JSON like snapshot_store.py
— this file is written on every single message, and SQLite handles that
kind of small frequent read/write far better than rewriting a whole JSON
file each time.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class ContextStore:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _get(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _set(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # -- update offset (getUpdates pagination) --------------------------
    def get_offset(self) -> int | None:
        value = self._get("update_offset")
        return int(value) if value is not None else None

    def set_offset(self, offset: int) -> None:
        self._set("update_offset", str(offset))

    # -- last /tareas listing, for /resumen <n> --------------------------
    def get_last_listing(self) -> list[str]:
        value = self._get("last_listing")
        result: list[str] = json.loads(value) if value else []
        return result

    def set_last_listing(self, assignment_ids: list[str]) -> None:
        self._set("last_listing", json.dumps(assignment_ids))

    # -- which assignment free-form chat is currently about --------------
    def get_focus_assignment_id(self) -> str | None:
        return self._get("focus_assignment_id")

    def set_focus_assignment_id(self, assignment_id: str) -> None:
        self._set("focus_assignment_id", assignment_id)
