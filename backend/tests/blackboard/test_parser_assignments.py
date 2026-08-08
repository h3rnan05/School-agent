from datetime import UTC, datetime

from app.blackboard.dto import AssignmentTimingStatus, DueDateStatus, FieldStatus
from app.blackboard.parser import parse_assignments_page

BASE_URL = "https://university.blackboard.com"
COURSE_ID = "_12345_1"
FIXED_NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def _by_title(assignments, title):
    return next(a for a in assignments if a.title == title)


def test_extracts_due_date_points_attachments_and_rubric_ref(load_fixture):
    html = load_fixture("assignments_original.html")
    result = parse_assignments_page(html, COURSE_ID, BASE_URL, timezone="UTC", now=FIXED_NOW)

    homework = _by_title(result, "Chapter 4 Homework")
    assert homework.due_date_status == DueDateStatus.OK
    assert homework.due_date is not None
    assert homework.due_date.year == 2026
    assert homework.due_date.month == 8
    assert homework.due_date.day == 12
    assert homework.points == 50.0
    assert homework.points_status == FieldStatus.OK
    assert homework.rubric_ref == "rubric"
    assert len(homework.attachments) == 1
    assert homework.attachments[0].filename == "chapter4_worksheet.pdf"
    assert homework.attachments[0].file_type == "pdf"
    assert homework.course_id == COURSE_ID


def test_missing_due_date_is_not_invented(load_fixture):
    html = load_fixture("assignments_original.html")
    result = parse_assignments_page(html, COURSE_ID, BASE_URL, timezone="UTC", now=FIXED_NOW)

    discussion = _by_title(result, "Discussion: Introduce Yourself")
    assert discussion.due_date is None
    assert discussion.due_date_status == DueDateStatus.NO_DUE_DATE
    assert discussion.timing_status == AssignmentTimingStatus.NO_DUE_DATE


def test_unparseable_due_date_is_flagged_not_guessed(load_fixture):
    html = load_fixture("assignments_original.html")
    result = parse_assignments_page(html, COURSE_ID, BASE_URL, timezone="UTC", now=FIXED_NOW)

    project = _by_title(result, "Group Project Kickoff")
    assert project.due_date is None
    assert project.due_date_status == DueDateStatus.UNPARSEABLE
    assert project.due_date_raw is not None  # original text preserved for debugging
    assert project.timing_status == AssignmentTimingStatus.UNKNOWN


def test_missing_points_is_not_present_not_zero(load_fixture):
    html = load_fixture("assignments_original.html")
    result = parse_assignments_page(html, COURSE_ID, BASE_URL, timezone="UTC", now=FIXED_NOW)

    quiz = _by_title(result, "Midterm Quiz")
    assert quiz.points is None
    assert quiz.points_status == FieldStatus.NOT_PRESENT


def test_item_without_a_link_is_skipped_not_crashed(load_fixture):
    html = load_fixture("assignments_original.html")
    result = parse_assignments_page(html, COURSE_ID, BASE_URL, timezone="UTC", now=FIXED_NOW)
    titles = [a.title for a in result]
    assert "" not in titles
    assert len(result) == 4  # 5 items in fixture, 1 has no link


def test_no_items_returns_empty_list_not_error(load_fixture):
    html = load_fixture("assignments_no_items.html")
    result = parse_assignments_page(html, COURSE_ID, BASE_URL, timezone="UTC", now=FIXED_NOW)
    assert result == []


def test_malformed_html_does_not_crash(load_fixture):
    html = load_fixture("assignments_malformed.html")
    result = parse_assignments_page(html, COURSE_ID, BASE_URL, timezone="UTC", now=FIXED_NOW)
    # BeautifulSoup repairs unclosed tags; we only assert this never raises
    # and returns a list (possibly partial) rather than throwing.
    assert isinstance(result, list)


def test_timing_status_upcoming_vs_overdue(load_fixture):
    html = load_fixture("assignments_original.html")
    result = parse_assignments_page(html, COURSE_ID, BASE_URL, timezone="UTC", now=FIXED_NOW)

    homework = _by_title(result, "Chapter 4 Homework")  # due Aug 12, now is Aug 8
    assert homework.timing_status == AssignmentTimingStatus.UPCOMING

    quiz = _by_title(result, "Midterm Quiz")  # due Aug 9 08:00, now is Aug 8 12:00
    assert quiz.timing_status == AssignmentTimingStatus.UPCOMING
