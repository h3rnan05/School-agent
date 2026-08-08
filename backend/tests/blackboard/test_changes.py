from datetime import UTC, datetime

import pytest

from app.blackboard.changes import diff_assignments
from tests.blackboard.factories import make_assignment


def test_no_changes_returns_empty_list():
    old = make_assignment()
    new = make_assignment()
    assert diff_assignments(old, new) == []


def test_detects_due_date_change():
    old = make_assignment()
    new = make_assignment(due_date=datetime(2026, 8, 12, 23, 59, tzinfo=UTC))

    changes = diff_assignments(old, new)
    assert len(changes) == 1
    assert changes[0].field == "due_date"
    assert changes[0].old_value == old.due_date
    assert changes[0].new_value == new.due_date


def test_detects_multiple_field_changes():
    old = make_assignment()
    new = make_assignment(title="Chapter 4 Homework (Updated)", points=60.0)

    changes = diff_assignments(old, new)
    fields_changed = {c.field for c in changes}
    assert fields_changed == {"title", "points"}


def test_rejects_diff_across_different_assignments():
    old = make_assignment(id="_content_9001")
    new = make_assignment(id="_content_9002")
    with pytest.raises(ValueError):
        diff_assignments(old, new)
