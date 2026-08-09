"""Configuration for the Telegram integration (Phase 3).

Same pattern as blackboard/config.py: nothing hardcoded, everything read
from the environment. TELEGRAM_CHAT_ID doubles as the allowlist — see
telegram_bot/bot.py, which refuses to act on any other chat id even if the
bot token leaks.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramSettings:
    bot_token: str
    chat_id: str


def load_telegram_settings() -> TelegramSettings:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set. "
            "Create a bot via @BotFather, message it once, then read your "
            "chat id from https://api.telegram.org/bot<token>/getUpdates."
        )
    return TelegramSettings(bot_token=bot_token, chat_id=chat_id)
