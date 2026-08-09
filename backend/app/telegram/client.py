"""Minimal Telegram Bot API client — send messages, long-poll for updates.

Uses only the standard library (urllib) rather than adding a new HTTP
dependency; the Bot API surface this module needs (sendMessage, getUpdates)
is small enough that a full SDK isn't worth the extra dependency.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

API_BASE = "https://api.telegram.org"
DEFAULT_TIMEOUT_SECONDS = 10
MAX_MESSAGE_LENGTH = 4096  # Telegram's hard limit per sendMessage call.


class TelegramError(Exception):
    """The Telegram Bot API was unreachable, or rejected a request."""


def _call(bot_token: str, method: str, params: dict, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    url = f"{API_BASE}/bot{bot_token}/{method}"
    payload = json.dumps(params).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise TelegramError(f"Could not reach the Telegram API ({method}): {exc}") from exc

    if not body.get("ok"):
        raise TelegramError(f"Telegram API rejected {method}: {body}")
    return body["result"]


def send_message(bot_token: str, chat_id: str, text: str) -> None:
    """Sends a plain-text message to a chat. Long text is truncated (with a
    visible marker) rather than silently rejected by Telegram's 4096-char
    per-message limit."""
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[: MAX_MESSAGE_LENGTH - 15] + "\n[...truncated]"
    _call(bot_token, "sendMessage", {"chat_id": chat_id, "text": text})


def get_updates(bot_token: str, offset: int | None = None, timeout: int = 25) -> list[dict]:
    """Long-polls for new updates. Pass `offset` = last processed update_id
    + 1 so Telegram doesn't redeliver updates already handled."""
    params: dict = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    result = _call(bot_token, "getUpdates", params, timeout=timeout + DEFAULT_TIMEOUT_SECONDS)
    return list(result)
