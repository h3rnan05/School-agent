"""No real network calls — urllib.request.urlopen is monkeypatched with a
fake response for every test, so this suite never talks to Telegram."""
from __future__ import annotations

import json

import pytest

from app.telegram import client


class _FakeResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_send_message_posts_expected_payload(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"ok": True, "result": {}})

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    client.send_message("TOKEN", "12345", "hola")

    assert captured["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert captured["body"] == {"chat_id": "12345", "text": "hola"}


def test_send_message_truncates_long_text(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"ok": True, "result": {}})

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    client.send_message("TOKEN", "12345", "x" * 5000)

    assert len(captured["body"]["text"]) <= client.MAX_MESSAGE_LENGTH
    assert captured["body"]["text"].endswith("[...truncated]")


def test_send_message_raises_telegram_error_when_api_rejects(monkeypatch):
    def fake_urlopen(request, timeout):
        return _FakeResponse({"ok": False, "description": "chat not found"})

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(client.TelegramError, match="chat not found"):
        client.send_message("TOKEN", "bad_chat", "hola")


def test_send_message_raises_telegram_error_on_network_failure(monkeypatch):
    def fake_urlopen(request, timeout):
        raise client.urllib.error.URLError("no network")

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(client.TelegramError, match="Could not reach"):
        client.send_message("TOKEN", "12345", "hola")


def test_get_updates_passes_offset_and_returns_result_list(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"ok": True, "result": [{"update_id": 1}, {"update_id": 2}]})

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    updates = client.get_updates("TOKEN", offset=42)

    assert captured["body"]["offset"] == 42
    assert updates == [{"update_id": 1}, {"update_id": 2}]


def test_get_updates_omits_offset_when_none(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"ok": True, "result": []})

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    client.get_updates("TOKEN")

    assert "offset" not in captured["body"]
