"""No real Anthropic API calls (and no real cost) — a fake client is
injected via the `client=` constructor argument for every test."""
from __future__ import annotations

from types import SimpleNamespace

from app.telegram_bot.claude_client import SYSTEM_PROMPT, ClaudeClient


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeAnthropic:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def _text_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_reply_extracts_text_from_response():
    fake = _FakeAnthropic(_text_response("Claro, te ayudo con eso."))
    client = ClaudeClient(client=fake)

    result = client.reply(context="Tarea: X", user_message="ayudame")

    assert result == "Claro, te ayudo con eso."


def test_reply_sends_system_prompt_and_context_and_message():
    fake = _FakeAnthropic(_text_response("ok"))
    client = ClaudeClient(client=fake)

    client.reply(context="Tarea: Actividad 2, materia Derecho", user_message="que pide?")

    call = fake.messages.calls[0]
    assert call["system"] == SYSTEM_PROMPT
    user_content = call["messages"][0]["content"]
    assert "Actividad 2" in user_content
    assert "que pide?" in user_content


def test_reply_concatenates_multiple_text_blocks():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Parte uno. "),
            SimpleNamespace(type="text", text="Parte dos."),
        ]
    )
    fake = _FakeAnthropic(response)
    client = ClaudeClient(client=fake)

    result = client.reply(context="", user_message="hola")

    assert result == "Parte uno. Parte dos."


def test_reply_ignores_non_text_blocks():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", text="internal reasoning, not shown"),
            SimpleNamespace(type="text", text="respuesta final"),
        ]
    )
    fake = _FakeAnthropic(response)
    client = ClaudeClient(client=fake)

    result = client.reply(context="", user_message="hola")

    assert result == "respuesta final"
