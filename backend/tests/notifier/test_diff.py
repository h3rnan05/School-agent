from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from app.notifier.diff import classify
from tests.blackboard.factories import make_assignment


def test_assignment_not_in_previous_snapshot_is_new():
    assignment = make_assignment(id="_1")

    events = classify(previous={}, found=[assignment])

    assert len(events) == 1
    assert events[0].kind == "NEW"
    assert events[0].assignment is assignment


def test_unchanged_assignment_produces_no_event():
    assignment = make_assignment(id="_1")

    events = classify(previous={"_1": assignment}, found=[assignment])

    assert events == []


def test_due_date_change_is_reported_with_old_value():
    old = make_assignment(id="_1", due_date=datetime(2026, 8, 10, 23, 59, tzinfo=timezone.utc))
    new = replace(old, due_date=datetime(2026, 8, 15, 23, 59, tzinfo=timezone.utc))

    events = classify(previous={"_1": old}, found=[new])

    assert len(events) == 1
    assert events[0].kind == "DUE_DATE_CHANGED"
    assert events[0].old_due_date == datetime(2026, 8, 10, 23, 59, tzinfo=timezone.utc)
    assert events[0].assignment.due_date == datetime(2026, 8, 15, 23, 59, tzinfo=timezone.utc)


def test_title_only_change_produces_no_event_notifier_only_cares_about_due_dates():
    old = make_assignment(id="_1", title="Old title")
    new = make_assignment(id="_1", title="New title")

    events = classify(previous={"_1": old}, found=[new])

    assert events == []
