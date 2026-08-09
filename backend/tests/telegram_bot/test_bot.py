"""No real Blackboard provider, Telegram network call, or Claude call in
this suite — everything is faked at the module boundary."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.blackboard.dto import UpcomingAssignments
from app.blackboard.exceptions import BlackboardUnavailableError
from app.blackboard.provider import BlackboardProvider, ProviderHealth, SessionHandle
from app.telegram.client import TelegramError
from app.telegram.config import TelegramSettings
from app.telegram_bot import bot
from app.telegram_bot.context_store import ContextStore
from tests.blackboard.factories import make_assignment, make_course


class FakeProvider(BlackboardProvider):
    def __init__(self, courses=None, upcoming=None, overdue=None, no_due_date=None, fail=False):
        self._courses = courses or []
        self._upcoming = upcoming or []
        self._overdue = overdue or []
        self._no_due_date = no_due_date or []
        self._fail = fail

    def login(self):
        return SessionHandle(authenticated=True, username="fake", created_at=datetime.now(timezone.utc))

    def is_session_valid(self):
        return True

    def get_current_user(self):
        return "fake"

    def get_courses(self):
        if self._fail:
            raise BlackboardUnavailableError("simulated outage")
        return self._courses

    def get_assignments(self, course_id):
        return []

    def get_upcoming_assignments(self, days=7, include_overdue=False, include_no_due_date=False):
        if self._fail:
            raise BlackboardUnavailableError("simulated outage")
        return UpcomingAssignments(
            upcoming=tuple(self._upcoming),
            overdue=tuple(self._overdue),
            no_due_date=tuple(self._no_due_date),
        )

    def health_check(self):
        return ProviderHealth(ok=True, message="fake", checked_at=datetime.now(timezone.utc))


class _FakeClaudeClient:
    def reply(self, context: str, user_message: str) -> str:
        return f"claude-reply-to:{user_message}"


@pytest.fixture
def store(tmp_path):
    return ContextStore(tmp_path / "state.sqlite3")


@pytest.fixture
def telegram_settings():
    return TelegramSettings(bot_token="TOKEN", chat_id="5054988412")


# -- _command_token ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/tareas", "/tareas"),
        ("/tareas@udemhomeworkbot", "/tareas"),
        ("/resumen 2", "/resumen"),
        ("hola como estas", "hola"),
        ("", ""),
    ],
)
def test_command_token(text, expected):
    assert bot._command_token(text) == expected


# -- route_message ---------------------------------------------------------


def test_route_message_tareas(store):
    course = make_course(id="_1", name="FINC 301")
    upcoming = [make_assignment(id="_a1", course_id="_1", title="Homework")]
    provider = FakeProvider(courses=[course], upcoming=upcoming)

    reply = bot.route_message("/tareas", provider, store, _FakeClaudeClient())

    assert "Homework" in reply
    assert store.get_last_listing() == ["_a1"]


def test_route_message_proxima(store):
    course = make_course(id="_1")
    upcoming = [make_assignment(id="_a1", course_id="_1", title="Homework")]
    provider = FakeProvider(courses=[course], upcoming=upcoming)

    reply = bot.route_message("/proxima", provider, store, _FakeClaudeClient())

    assert "Homework" in reply


def test_route_message_resumen(store):
    course = make_course(id="_1")
    upcoming = [make_assignment(id="_a1", course_id="_1", title="Homework")]
    provider = FakeProvider(courses=[course], upcoming=upcoming)
    bot.route_message("/tareas", provider, store, _FakeClaudeClient())  # populate listing

    reply = bot.route_message("/resumen 1", provider, store, _FakeClaudeClient())

    assert "Homework" in reply
    assert store.get_focus_assignment_id() == "_a1"


def test_route_message_start(store):
    provider = FakeProvider()

    reply = bot.route_message("/start", provider, store, _FakeClaudeClient())

    assert "Hola!" in reply
    assert "/tareas" in reply


def test_route_message_free_text_goes_to_claude(store):
    provider = FakeProvider()

    reply = bot.route_message("ayudame con esto", provider, store, _FakeClaudeClient())

    assert reply == "claude-reply-to:ayudame con esto"


def test_route_message_blackboard_failure_does_not_crash(store):
    provider = FakeProvider(fail=True)

    reply = bot.route_message("/tareas", provider, store, _FakeClaudeClient())

    assert "No pude leer Blackboard" in reply


# -- handle_update -----------------------------------------------------


def test_handle_update_ignores_unauthorized_chat_id(monkeypatch, store, telegram_settings):
    sent = []
    monkeypatch.setattr(bot, "send_message", lambda token, chat_id, text: sent.append((chat_id, text)))
    provider = FakeProvider()
    update = {"message": {"chat": {"id": 999999}, "text": "/tareas"}}

    bot.handle_update(update, provider, store, _FakeClaudeClient(), telegram_settings)

    assert sent == []


def test_handle_update_replies_to_authorized_chat(monkeypatch, store, telegram_settings):
    sent = []
    monkeypatch.setattr(bot, "send_message", lambda token, chat_id, text: sent.append((chat_id, text)))
    provider = FakeProvider()
    update = {"message": {"chat": {"id": 5054988412}, "text": "/start"}}

    bot.handle_update(update, provider, store, _FakeClaudeClient(), telegram_settings)

    assert len(sent) == 1
    assert sent[0][0] == "5054988412"
    assert "Hola!" in sent[0][1]


def test_handle_update_ignores_updates_without_a_message(monkeypatch, store, telegram_settings):
    sent = []
    monkeypatch.setattr(bot, "send_message", lambda token, chat_id, text: sent.append((chat_id, text)))
    provider = FakeProvider()
    update = {"edited_message": {"chat": {"id": 5054988412}, "text": "edited"}}

    bot.handle_update(update, provider, store, _FakeClaudeClient(), telegram_settings)

    assert sent == []


def test_handle_update_ignores_messages_without_text(monkeypatch, store, telegram_settings):
    sent = []
    monkeypatch.setattr(bot, "send_message", lambda token, chat_id, text: sent.append((chat_id, text)))
    provider = FakeProvider()
    update = {"message": {"chat": {"id": 5054988412}, "sticker": {}}}

    bot.handle_update(update, provider, store, _FakeClaudeClient(), telegram_settings)

    assert sent == []


def test_handle_update_swallows_send_failure(monkeypatch, store, telegram_settings):
    def failing_send(token, chat_id, text):
        raise TelegramError("simulated outage")

    monkeypatch.setattr(bot, "send_message", failing_send)
    provider = FakeProvider()
    update = {"message": {"chat": {"id": 5054988412}, "text": "/start"}}

    bot.handle_update(update, provider, store, _FakeClaudeClient(), telegram_settings)  # must not raise


# -- poll_once -----------------------------------------------------------


def test_poll_once_advances_offset_and_persists_it(monkeypatch, store, telegram_settings):
    monkeypatch.setattr(
        bot,
        "get_updates",
        lambda token, offset: [{"update_id": 10, "message": {"chat": {"id": 5054988412}, "text": "/start"}}],
    )
    monkeypatch.setattr(bot, "send_message", lambda token, chat_id, text: None)
    provider = FakeProvider()

    new_offset = bot.poll_once(provider, store, _FakeClaudeClient(), telegram_settings, offset=None)

    assert new_offset == 11
    assert store.get_offset() == 11


def test_poll_once_returns_same_offset_when_telegram_unreachable(monkeypatch, store, telegram_settings):
    def failing_get_updates(token, offset):
        raise TelegramError("simulated outage")

    monkeypatch.setattr(bot, "get_updates", failing_get_updates)
    provider = FakeProvider()

    new_offset = bot.poll_once(provider, store, _FakeClaudeClient(), telegram_settings, offset=7)

    assert new_offset == 7


def test_poll_once_with_no_new_updates_keeps_offset(monkeypatch, store, telegram_settings):
    monkeypatch.setattr(bot, "get_updates", lambda token, offset: [])
    provider = FakeProvider()

    new_offset = bot.poll_once(provider, store, _FakeClaudeClient(), telegram_settings, offset=3)

    assert new_offset == 3
