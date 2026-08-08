"""CLI tests use a fake BlackboardProvider — no Playwright, no real
Blackboard. They only verify the CLI wires provider output to console
output and to the change-detection cache correctly.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from click.testing import CliRunner

from app.blackboard import cli as cli_module
from app.blackboard.dto import Course, UpcomingAssignments
from app.blackboard.provider import BlackboardProvider, ProviderHealth, SessionHandle
from tests.blackboard.factories import make_assignment


class FakeProvider(BlackboardProvider):
    def __init__(self, courses=None, assignments=None):
        self._courses = courses or []
        self._assignments = assignments or []

    def login(self) -> SessionHandle:
        return SessionHandle(authenticated=True, username="fake_user", created_at=datetime.now(UTC))

    def is_session_valid(self) -> bool:
        return True

    def get_current_user(self) -> str | None:
        return "fake_user"

    def get_courses(self):
        return self._courses

    def get_assignments(self, course_id: str):
        return [a for a in self._assignments if a.course_id == course_id]

    def get_upcoming_assignments(self, days=7, include_overdue=False, include_no_due_date=False):
        return UpcomingAssignments(upcoming=tuple(self._assignments))

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(ok=True, message="fake", checked_at=datetime.now(UTC))


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACKBOARD_BASE_URL", "https://university.blackboard.com")
    monkeypatch.setenv("SCHOOL_AGENT_STATE_DIR", str(tmp_path))
    from app.blackboard.config import load_settings

    return load_settings()


def test_courses_command_prints_expected_fields(monkeypatch, settings):
    fake = FakeProvider(courses=[Course(id="_12345_1", name="Finance 301", url="https://x/course/1", term=None, source="playwright")])
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["courses"])

    assert result.exit_code == 0
    assert "COURSES FOUND" in result.output
    assert "course_id:   _12345_1" in result.output
    assert "course_name: Finance 301" in result.output


def test_assignments_command_prints_upcoming_fields(monkeypatch, settings):
    assignment = make_assignment(course_id="_12345_1")
    fake = FakeProvider(assignments=[assignment])
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["assignments", "_12345_1"])

    assert result.exit_code == 0
    assert "ASSIGNMENT: Chapter 4 Homework" in result.output
    assert "STATUS: UPCOMING" in result.output


def test_upcoming_command_reports_due_date_change_across_runs(monkeypatch, settings):
    first_run = make_assignment(course_id="_12345_1")
    fake_first = FakeProvider(assignments=[first_run])
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake_first)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)
    CliRunner().invoke(cli_module.cli, ["upcoming"])

    changed = make_assignment(
        course_id="_12345_1",
        due_date=datetime(2026, 8, 15, 23, 59, tzinfo=UTC),
    )
    fake_second = FakeProvider(assignments=[changed])
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake_second)

    result = CliRunner().invoke(cli_module.cli, ["upcoming"])

    assert result.exit_code == 0
    assert "[CHANGED]" in result.output
    assert "due date" in result.output
