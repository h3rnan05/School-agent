from __future__ import annotations

import pytest

from app.telegram.config import load_telegram_settings


def test_loads_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "5054988412")

    settings = load_telegram_settings()

    assert settings.bot_token == "123:ABC"
    assert settings.chat_id == "5054988412"


def test_raises_when_bot_token_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "5054988412")

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        load_telegram_settings()


def test_raises_when_chat_id_missing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(RuntimeError, match="TELEGRAM_CHAT_ID"):
        load_telegram_settings()
