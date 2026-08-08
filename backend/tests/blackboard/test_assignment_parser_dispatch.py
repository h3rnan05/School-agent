"""AssignmentParser routes by Course.course_view, never by the
institution's overall Blackboard Experience — the core Phase 2.1 fix."""
from datetime import UTC, datetime

from app.blackboard.dto import CourseView
from app.blackboard.parsers import AssignmentParser
from tests.blackboard.factories import make_course

BASE_URL = "https://university.blackboard.com"
FIXED_NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def test_routes_original_course_view_to_original_parser(load_fixture):
    html = load_fixture("assignments_original.html")
    course = make_course(id="_12345_1", course_view=CourseView.ORIGINAL)

    result = AssignmentParser().parse(html, course, BASE_URL, timezone="UTC", now=FIXED_NOW)

    assert len(result) == 4  # same fixture/result as OriginalCourseParser directly
    assert all(a.course_id == "_12345_1" for a in result)


def test_routes_ultra_course_view_to_ultra_stub(load_fixture):
    html = load_fixture("assignments_original.html")  # content is irrelevant, stub ignores it
    course = make_course(id="_98766_1", course_view=CourseView.ULTRA)

    result = AssignmentParser().parse(html, course, BASE_URL, timezone="UTC", now=FIXED_NOW)

    assert result == []  # UltraCourseParser stub — not "no assignments found"


def test_unknown_course_view_falls_back_to_original_as_disclosed_best_effort(load_fixture):
    html = load_fixture("assignments_original.html")
    course = make_course(id="_12345_1", course_view=CourseView.UNKNOWN)

    result = AssignmentParser().parse(html, course, BASE_URL, timezone="UTC", now=FIXED_NOW)

    assert len(result) == 4
