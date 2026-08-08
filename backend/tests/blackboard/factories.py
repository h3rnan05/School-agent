"""Shared test-data builders for the Blackboard module's test suite."""
from datetime import datetime, timezone
from typing import Any

from app.blackboard.dto import (
    Assignment,
    AssignmentKind,
    AssignmentTimingStatus,
    Course,
    CourseView,
    DueDateStatus,
    FieldStatus,
)


def make_assignment(**overrides: Any) -> Assignment:
    # Deliberately loosely typed: this is a test-only builder that accepts
    # any field override, so mypy can't narrow the **kwargs going into
    # Assignment(**defaults) — that's expected here, not a real type error.
    defaults: dict[str, Any] = dict(
        id="_content_9001",
        course_id="_12345_1",
        kind=AssignmentKind.ASSIGNMENT,
        title="Chapter 4 Homework",
        description=None,
        instructions=None,
        due_date=datetime(2026, 8, 10, 23, 59, tzinfo=timezone.utc),
        due_date_raw="August 10, 2026 11:59 PM",
        due_date_status=DueDateStatus.OK,
        timezone="UTC",
        points=50.0,
        points_status=FieldStatus.OK,
        url="https://university.blackboard.com/content/9001",
        timing_status=AssignmentTimingStatus.UPCOMING,
        rubric_ref=None,
    )
    defaults.update(overrides)
    return Assignment(**defaults)


def make_course(**overrides: Any) -> Course:
    defaults: dict[str, Any] = dict(
        id="_12345_1",
        name="FINANCE 301 - Corporate Finance",
        url="https://university.blackboard.com/ultra/courses/_12345_1/outline",
        term=None,
        course_view=CourseView.ORIGINAL,
        instructor=None,
        source="playwright",
    )
    defaults.update(overrides)
    return Course(**defaults)
