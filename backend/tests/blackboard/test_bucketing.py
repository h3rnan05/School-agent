from datetime import UTC, datetime, timedelta

from app.blackboard.dto import AssignmentTimingStatus, DueDateStatus
from app.blackboard.providers.playwright_provider import bucket_assignments
from tests.blackboard.factories import make_assignment


def relative_assignment(assignment_id: str, days_from_now: float | None, **overrides):
    if days_from_now is None:
        return make_assignment(
            id=assignment_id,
            due_date=None,
            due_date_raw=None,
            due_date_status=DueDateStatus.NO_DUE_DATE,
            timing_status=AssignmentTimingStatus.NO_DUE_DATE,
            **overrides,
        )
    due = datetime.now(UTC) + timedelta(days=days_from_now)
    return make_assignment(
        id=assignment_id,
        due_date=due,
        due_date_raw=due.isoformat(),
        due_date_status=DueDateStatus.OK,
        **overrides,
    )


def test_upcoming_within_window():
    assignments = [relative_assignment("a1", 2), relative_assignment("a2", 10)]
    result = bucket_assignments(assignments, days=7, include_overdue=False, include_no_due_date=False)
    ids = {a.id for a in result.upcoming}
    assert ids == {"a1"}
    assert result.overdue == ()
    assert result.no_due_date == ()


def test_overdue_excluded_unless_requested():
    assignments = [relative_assignment("a1", -1)]

    default_result = bucket_assignments(assignments, days=7, include_overdue=False, include_no_due_date=False)
    assert default_result.upcoming == ()
    assert default_result.overdue == ()  # overdue exists but is not silently included anywhere

    with_overdue = bucket_assignments(assignments, days=7, include_overdue=True, include_no_due_date=False)
    assert {a.id for a in with_overdue.overdue} == {"a1"}
    assert with_overdue.upcoming == ()  # never mixed into the main bucket


def test_no_due_date_excluded_unless_requested():
    assignments = [relative_assignment("a1", None)]

    default_result = bucket_assignments(assignments, days=7, include_overdue=False, include_no_due_date=False)
    assert default_result.no_due_date == ()
    assert default_result.upcoming == ()

    with_no_due_date = bucket_assignments(assignments, days=7, include_overdue=False, include_no_due_date=True)
    assert {a.id for a in with_no_due_date.no_due_date} == {"a1"}


def test_buckets_never_overlap():
    assignments = [
        relative_assignment("upcoming", 3),
        relative_assignment("overdue", -3),
        relative_assignment("none", None),
    ]
    result = bucket_assignments(assignments, days=7, include_overdue=True, include_no_due_date=True)

    all_ids = [a.id for a in result.upcoming] + [a.id for a in result.overdue] + [a.id for a in result.no_due_date]
    assert len(all_ids) == len(set(all_ids))  # no assignment appears in two buckets
