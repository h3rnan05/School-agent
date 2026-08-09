"""notifier `run-once` — uses fake Blackboard/Telegram at the module's
import boundary (app.notifier.cli.*), never a real provider, network call,
or Telegram API." No live Blackboard, no live Telegram in this suite.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from app.blackboard.dto import UpcomingAssignments
from app.blackboard.exceptions import BlackboardUnavailableError
from app.blackboard.provider import BlackboardProvider, ProviderHealth, SessionHandle
from app.blackboard.snapshot_store import SnapshotStore
from app.notifier import cli as notifier_cli
from app.telegram.client import TelegramError
from app.telegram.config import TelegramSettings
from tests.blackboard.factories import make_assignment, make_course


class FakeProvider(BlackboardProvider):
    def __init__(self, courses=None, assignments=None, fail=False):
        self._courses = courses or []
        self._assignments = assignments or []
        self._fail = fail

    def login(self) -> SessionHandle:
        return SessionHandle(authenticated=True, username="fake_user", created_at=datetime.now(timezone.utc))

    def is_session_valid(self) -> bool:
        return True

    def get_current_user(self):
        return "fake_user"

    def get_courses(self):
        if self._fail:
            raise BlackboardUnavailableError("simulated outage")
        return self._courses

    def get_assignments(self, course_id: str):
        return [a for a in self._assignments if a.course_id == course_id]

    def get_upcoming_assignments(self, days=7, include_overdue=False, include_no_due_date=False):
        if self._fail:
            raise BlackboardUnavailableError("simulated outage")
        return UpcomingAssignments(
            upcoming=(), overdue=(), no_due_date=tuple(self._assignments)
        )

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(ok=True, message="fake", checked_at=datetime.now(timezone.utc))


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACKBOARD_BASE_URL", "https://university.blackboard.com")
    monkeypatch.setenv("SCHOOL_AGENT_STATE_DIR", str(tmp_path))
    from app.blackboard.config import load_settings

    return load_settings()


@pytest.fixture
def telegram_settings():
    return TelegramSettings(bot_token="TOKEN", chat_id="12345")


def _patch_common(monkeypatch, settings, telegram_settings, provider):
    monkeypatch.setattr(notifier_cli, "load_settings", lambda: settings)
    monkeypatch.setattr(notifier_cli, "load_telegram_settings", lambda: telegram_settings)
    monkeypatch.setattr(notifier_cli, "get_provider", lambda s: provider)


def test_first_run_saves_baseline_and_sends_no_messages(monkeypatch, settings, telegram_settings):
    course = make_course(id="_1")
    assignment = make_assignment(id="_a1", course_id="_1")
    provider = FakeProvider(courses=[course], assignments=[assignment])
    _patch_common(monkeypatch, settings, telegram_settings, provider)

    sent = []
    monkeypatch.setattr(notifier_cli, "send_message", lambda token, chat_id, text: sent.append(text))

    result = CliRunner().invoke(notifier_cli.cli, ["run-once"])

    assert result.exit_code == 0
    assert sent == []
    cached = SnapshotStore(settings.snapshot_cache_path).load()
    assert "_a1" in cached


def test_second_run_notifies_about_new_assignment(monkeypatch, settings, telegram_settings):
    course = make_course(id="_1")
    existing = make_assignment(id="_a1", course_id="_1")
    provider_first = FakeProvider(courses=[course], assignments=[existing])
    _patch_common(monkeypatch, settings, telegram_settings, provider_first)
    monkeypatch.setattr(notifier_cli, "send_message", lambda *a, **k: None)
    CliRunner().invoke(notifier_cli.cli, ["run-once"])  # establishes baseline

    new_assignment = make_assignment(id="_a2", course_id="_1", title="Brand new task")
    provider_second = FakeProvider(courses=[course], assignments=[existing, new_assignment])
    monkeypatch.setattr(notifier_cli, "get_provider", lambda s: provider_second)
    sent = []
    monkeypatch.setattr(notifier_cli, "send_message", lambda token, chat_id, text: sent.append(text))

    result = CliRunner().invoke(notifier_cli.cli, ["run-once"])

    assert result.exit_code == 0
    assert len(sent) == 1
    assert "Brand new task" in sent[0]
    assert "Tarea nueva" in sent[0]


def test_second_run_notifies_about_due_date_change(monkeypatch, settings, telegram_settings):
    course = make_course(id="_1")
    original = make_assignment(id="_a1", course_id="_1", due_date=datetime(2026, 8, 10, 23, 59, tzinfo=timezone.utc))
    provider_first = FakeProvider(courses=[course], assignments=[original])
    _patch_common(monkeypatch, settings, telegram_settings, provider_first)
    monkeypatch.setattr(notifier_cli, "send_message", lambda *a, **k: None)
    CliRunner().invoke(notifier_cli.cli, ["run-once"])  # baseline

    from dataclasses import replace

    changed = replace(original, due_date=datetime(2026, 8, 20, 23, 59, tzinfo=timezone.utc))
    provider_second = FakeProvider(courses=[course], assignments=[changed])
    monkeypatch.setattr(notifier_cli, "get_provider", lambda s: provider_second)
    sent = []
    monkeypatch.setattr(notifier_cli, "send_message", lambda token, chat_id, text: sent.append(text))

    result = CliRunner().invoke(notifier_cli.cli, ["run-once"])

    assert result.exit_code == 0
    assert len(sent) == 1
    assert "Cambió la fecha" in sent[0]


def test_blackboard_failure_sends_failure_notification_and_exits_nonzero(monkeypatch, settings, telegram_settings):
    provider = FakeProvider(fail=True)
    _patch_common(monkeypatch, settings, telegram_settings, provider)
    sent = []
    monkeypatch.setattr(notifier_cli, "send_message", lambda token, chat_id, text: sent.append(text))

    result = CliRunner().invoke(notifier_cli.cli, ["run-once"])

    assert result.exit_code == 1
    assert len(sent) == 1
    assert "No pude revisar Blackboard" in sent[0]


def test_telegram_failure_while_notifying_does_not_crash_or_lose_other_events(
    monkeypatch, settings, telegram_settings
):
    course = make_course(id="_1")
    existing = make_assignment(id="_a1", course_id="_1")
    provider_first = FakeProvider(courses=[course], assignments=[existing])
    _patch_common(monkeypatch, settings, telegram_settings, provider_first)
    monkeypatch.setattr(notifier_cli, "send_message", lambda *a, **k: None)
    CliRunner().invoke(notifier_cli.cli, ["run-once"])  # baseline

    new_assignment = make_assignment(id="_a2", course_id="_1")
    provider_second = FakeProvider(courses=[course], assignments=[existing, new_assignment])
    monkeypatch.setattr(notifier_cli, "get_provider", lambda s: provider_second)

    def failing_send(token, chat_id, text):
        raise TelegramError("simulated telegram outage")

    monkeypatch.setattr(notifier_cli, "send_message", failing_send)

    result = CliRunner().invoke(notifier_cli.cli, ["run-once"])

    assert result.exit_code == 0  # a failed notification is logged, not fatal
    cached = SnapshotStore(settings.snapshot_cache_path).load()
    assert "_a2" in cached  # the cache still advances so we don't re-try forever
