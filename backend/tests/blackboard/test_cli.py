"""CLI tests use a fake BlackboardProvider — no Playwright, no real
Blackboard. They only verify the CLI wires provider output to console
output and to the change-detection cache correctly.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from app.blackboard import cli as cli_module
from app.blackboard.dto import CourseView, UpcomingAssignments
from app.blackboard.provider import BlackboardProvider, ProviderHealth, SessionHandle
from tests.blackboard.factories import make_assignment, make_course


class FakeProvider(BlackboardProvider):
    def __init__(self, courses=None, assignments=None):
        self._courses = courses or []
        self._assignments = assignments or []

    def login(self) -> SessionHandle:
        return SessionHandle(authenticated=True, username="fake_user", created_at=datetime.now(timezone.utc))

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
        return ProviderHealth(ok=True, message="fake", checked_at=datetime.now(timezone.utc))


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACKBOARD_BASE_URL", "https://university.blackboard.com")
    monkeypatch.setenv("SCHOOL_AGENT_STATE_DIR", str(tmp_path))
    from app.blackboard.config import load_settings

    return load_settings()


def test_courses_command_prints_expected_fields(monkeypatch, settings):
    course = make_course(
        id="_12345_1",
        name="Finance 301",
        url="https://x/course/1",
        course_view=CourseView.ORIGINAL,
        instructor="Dr. Maria Gonzalez",
    )
    fake = FakeProvider(courses=[course])
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["courses"])

    assert result.exit_code == 0
    assert "COURSES FOUND" in result.output
    assert "course_id:   _12345_1" in result.output
    assert "course_name: Finance 301" in result.output
    assert "course_view: ORIGINAL" in result.output
    assert "instructor:  Dr. Maria Gonzalez" in result.output


def test_courses_command_flags_unknown_course_view(monkeypatch, settings):
    course = make_course(course_view=CourseView.UNKNOWN, instructor=None)
    fake = FakeProvider(courses=[course])
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["courses"])

    assert result.exit_code == 0
    assert "course_view: UNKNOWN" in result.output
    assert "Note: course_view could not be determined for 1 course(s)" in result.output


def test_assignments_command_prints_expected_fields(monkeypatch, settings):
    course = make_course(id="_12345_1", name="Finance 301", course_view=CourseView.ORIGINAL)
    assignment = make_assignment(course_id="_12345_1")
    fake = FakeProvider(courses=[course], assignments=[assignment])
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["assignments", "_12345_1"])

    assert result.exit_code == 0
    assert "COURSE: Finance 301" in result.output
    assert "ASSIGNMENT: Chapter 4 Homework" in result.output
    assert "DUE DATE: August 10, 2026" in result.output
    assert "TIME: 11:59 PM" in result.output
    assert "TIMEZONE: UTC" in result.output
    assert "POINTS: 50 points" in result.output
    assert "COURSE VIEW: ORIGINAL" in result.output
    assert "STATUS: UPCOMING" in result.output


def test_assignments_command_falls_back_to_course_id_when_course_unknown(monkeypatch, settings):
    assignment = make_assignment(course_id="_99999_1")
    fake = FakeProvider(courses=[], assignments=[assignment])
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["assignments", "_99999_1"])

    assert result.exit_code == 0
    assert "COURSE: _99999_1" in result.output
    assert "COURSE VIEW: UNKNOWN" in result.output


def test_upcoming_command_reports_due_date_change_across_runs(monkeypatch, settings):
    course = make_course(id="_12345_1")
    first_run = make_assignment(course_id="_12345_1")
    fake_first = FakeProvider(courses=[course], assignments=[first_run])
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake_first)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)
    CliRunner().invoke(cli_module.cli, ["upcoming"])

    changed = make_assignment(
        course_id="_12345_1",
        due_date=datetime(2026, 8, 15, 23, 59, tzinfo=timezone.utc),
    )
    fake_second = FakeProvider(courses=[course], assignments=[changed])
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake_second)

    result = CliRunner().invoke(cli_module.cli, ["upcoming"])

    assert result.exit_code == 0
    assert "[CHANGED]" in result.output
    assert "due date" in result.output
