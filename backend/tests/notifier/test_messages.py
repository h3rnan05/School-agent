from __future__ import annotations

from datetime import datetime, timezone

from app.notifier.diff import NotifierEvent
from app.notifier.messages import format_event
from tests.blackboard.factories import make_assignment, make_course


def test_new_assignment_message_includes_course_name_and_due_date():
    course = make_course(id="_12345_1", name="FINC 301 - Corporate Finance")
    assignment = make_assignment(course_id="_12345_1", title="Chapter 4 Homework")
    event = NotifierEvent(kind="NEW", assignment=assignment)

    text = format_event(event, course_map={"_12345_1": course})

    assert "Tarea nueva" in text
    assert "FINC 301 - Corporate Finance" in text
    assert "Chapter 4 Homework" in text
    assert "August 10, 2026" in text


def test_new_assignment_message_falls_back_to_course_id_when_course_unknown():
    assignment = make_assignment(course_id="_99999_1")
    event = NotifierEvent(kind="NEW", assignment=assignment)

    text = format_event(event, course_map={})

    assert "_99999_1" in text


def test_due_date_changed_message_shows_old_and_new():
    course = make_course(id="_12345_1", name="FINC 301")
    assignment = make_assignment(
        course_id="_12345_1",
        due_date=datetime(2026, 8, 15, 23, 59, tzinfo=timezone.utc),
    )
    event = NotifierEvent(
        kind="DUE_DATE_CHANGED",
        assignment=assignment,
        old_due_date=datetime(2026, 8, 10, 23, 59, tzinfo=timezone.utc),
    )

    text = format_event(event, course_map={"_12345_1": course})

    assert "Cambió la fecha" in text
    assert "2026-08-10" in text
    assert "August 15, 2026" in text


def test_due_date_changed_message_handles_previously_missing_due_date():
    assignment = make_assignment()
    event = NotifierEvent(kind="DUE_DATE_CHANGED", assignment=assignment, old_due_date=None)

    text = format_event(event, course_map={})

    assert "(sin fecha)" in text
