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


class FakeProviderWithDump(FakeProvider):
    def dump_courses_html(self, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("<html>fake dump</html>", encoding="utf-8")
        return output_path


def test_debug_dump_courses_html_reports_saved_path(monkeypatch, settings):
    fake = FakeProviderWithDump()
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["debug-dump-courses-html"])

    assert result.exit_code == 0
    assert "Saved the course list page's HTML to:" in result.output
    assert str(settings.debug_html_dir / "courses_page.html") in result.output


def test_debug_dump_courses_html_unavailable_on_providers_without_it(monkeypatch, settings):
    fake = FakeProvider()  # no dump_courses_html method
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["debug-dump-courses-html"])

    assert result.exit_code == 1
    assert "only available with the Playwright provider" in result.output


class _FakeCourseDumpResult:
    def __init__(self, **kwargs):
        self.html_path = kwargs["html_path"]
        self.course_url = kwargs["course_url"]
        self.url_before_content_link = kwargs["url_before_content_link"]
        self.content_link_followed = kwargs["content_link_followed"]
        self.follow_link_text_requested = kwargs.get("follow_link_text_requested")
        self.follow_link_result = kwargs.get("follow_link_result")
        self.final_url = kwargs["final_url"]


class FakeProviderWithCourseDump(FakeProvider):
    def dump_course_html(self, course_id, output_path, follow_link_text=None):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("<html>fake course dump</html>", encoding="utf-8")
        return _FakeCourseDumpResult(
            html_path=output_path,
            course_url="https://x/course/outline",
            url_before_content_link="https://x/course/outline",
            content_link_followed="https://x/course/content",
            follow_link_text_requested=follow_link_text,
            follow_link_result="https://x/course/content/assessments" if follow_link_text else None,
            final_url="https://x/course/content/assessments" if follow_link_text else "https://x/course/content",
        )


def test_debug_dump_course_html_reports_urls(monkeypatch, settings):
    fake = FakeProviderWithCourseDump()
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["debug-dump-course-html", "_12345_1"])

    assert result.exit_code == 0
    assert "Saved the course page's HTML to:" in result.output
    assert "https://x/course/outline" in result.output
    assert "Followed a link matching" in result.output
    assert "https://x/course/content" in result.output


def test_debug_dump_course_html_with_follow_reports_the_extra_link(monkeypatch, settings):
    fake = FakeProviderWithCourseDump()
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(
        cli_module.cli, ["debug-dump-course-html", "_12345_1", "--follow", "Assessments"]
    )

    assert result.exit_code == 0
    assert "Followed --follow 'Assessments'" in result.output
    assert "https://x/course/content/assessments" in result.output


def test_debug_dump_course_html_unavailable_on_providers_without_it(monkeypatch, settings):
    fake = FakeProvider()  # no dump_course_html method
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["debug-dump-course-html", "_12345_1"])

    assert result.exit_code == 1
    assert "only available with the Playwright provider" in result.output


class FakeProviderWithUrlDump(FakeProvider):
    def dump_url_html(self, url, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("<html>fake url dump</html>", encoding="utf-8")
        return output_path


def test_debug_dump_url_reports_saved_path(monkeypatch, settings):
    fake = FakeProviderWithUrlDump()
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["debug-dump-url", "https://x/webapps/assignment/uploadAssignment"])

    assert result.exit_code == 0
    assert "Saved to:" in result.output


def test_debug_dump_url_reports_value_error_from_host_check(monkeypatch, settings):
    class FakeProviderRejectsUrl(FakeProvider):
        def dump_url_html(self, url, output_path):
            raise ValueError(f"Refusing to navigate to {url!r}: host mismatch.")

    fake = FakeProviderRejectsUrl()
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["debug-dump-url", "https://attacker.example.com/steal"])

    assert result.exit_code == 1
    assert "Could not dump that URL" in result.output


def test_debug_dump_url_unavailable_on_providers_without_it(monkeypatch, settings):
    fake = FakeProvider()  # no dump_url_html method
    monkeypatch.setattr(cli_module, "get_provider", lambda s: fake)
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.cli, ["debug-dump-url", "https://x/some/page"])

    assert result.exit_code == 1
    assert "only available with the Playwright provider" in result.output
