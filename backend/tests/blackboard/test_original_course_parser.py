from datetime import datetime, timezone

from app.blackboard.dto import AssignmentTimingStatus, DueDateStatus, FieldStatus
from app.blackboard.parsers import OriginalCourseParser

BASE_URL = "https://university.blackboard.com"
COURSE_ID = "_12345_1"
FIXED_NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def _by_title(assignments, title):
    return next(a for a in assignments if a.title == title)


def _parse(html):
    return OriginalCourseParser().parse(html, COURSE_ID, BASE_URL, timezone="UTC", now=FIXED_NOW)


def test_extracts_due_date_points_attachments_and_rubric_ref(load_fixture):
    html = load_fixture("assignments_original.html")
    result = _parse(html)

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
    result = _parse(html)

    discussion = _by_title(result, "Discussion: Introduce Yourself")
    assert discussion.due_date is None
    assert discussion.due_date_status == DueDateStatus.NO_DUE_DATE
    assert discussion.timing_status == AssignmentTimingStatus.NO_DUE_DATE


def test_unparseable_due_date_is_flagged_not_guessed(load_fixture):
    html = load_fixture("assignments_original.html")
    result = _parse(html)

    project = _by_title(result, "Group Project Kickoff")
    assert project.due_date is None
    assert project.due_date_status == DueDateStatus.UNPARSEABLE
    assert project.due_date_raw is not None  # original text preserved for debugging
    assert project.timing_status == AssignmentTimingStatus.UNKNOWN


def test_missing_points_is_not_present_not_zero(load_fixture):
    html = load_fixture("assignments_original.html")
    result = _parse(html)

    quiz = _by_title(result, "Midterm Quiz")
    assert quiz.points is None
    assert quiz.points_status == FieldStatus.NOT_PRESENT


def test_item_without_a_link_is_skipped_not_crashed(load_fixture):
    html = load_fixture("assignments_original.html")
    result = _parse(html)
    titles = [a.title for a in result]
    assert "" not in titles
    assert len(result) == 4  # 5 items in fixture, 1 has no link


def test_no_items_returns_empty_list_not_error(load_fixture):
    html = load_fixture("assignments_no_items.html")
    result = _parse(html)
    assert result == []


def test_malformed_html_does_not_crash(load_fixture):
    html = load_fixture("assignments_malformed.html")
    result = _parse(html)
    assert isinstance(result, list)


def test_timing_status_upcoming_vs_overdue(load_fixture):
    html = load_fixture("assignments_original.html")
    result = _parse(html)

    homework = _by_title(result, "Chapter 4 Homework")  # due Aug 12, now is Aug 8
    assert homework.timing_status == AssignmentTimingStatus.UPCOMING

    quiz = _by_title(result, "Midterm Quiz")  # due Aug 9 08:00, now is Aug 8 12:00
    assert quiz.timing_status == AssignmentTimingStatus.UPCOMING


def test_course_menu_items_are_not_treated_as_assignments(load_fixture):
    """Real UDEM finding: the persistent left-nav course menu renders as
    <li id="paletteItem:_XXX_1"> — matches the broad li[id] selector, but
    is navigation, not content. Must come back empty, not fake assignments
    named "Home Page" / "My Grades" with no due dates."""
    html = load_fixture("course_menu_udem_palette.html")
    result = _parse(html)
    assert result == []


def test_menu_item_without_a_link_does_not_produce_a_warning_crash(load_fixture):
    """paletteItem:_3534779_1 in the fixture has no <a> at all — must be
    filtered out with the rest of the menu, not hit the "no link" path."""
    html = load_fixture("course_menu_udem_palette.html")
    result = _parse(html)  # must not raise
    assert isinstance(result, list)


def test_real_content_items_are_extracted_by_confirmed_id_prefix(load_fixture):
    """Confirmed real UDEM markup (inside an actual content area): real
    items use id="contentListItem:_XXX_1" / class="clearfix liItem read".
    Toolbar buttons (secondaryButton, icon-only) in the same fixture must
    be excluded, not produce "no extractable title" noise."""
    html = load_fixture("course_content_udem_real_structure.html")
    result = _parse(html)

    titles = {a.title for a in result}
    assert titles == {"Experiencias de aprendizaje 1er. Parcial", "Actividad integradora 2"}


def test_real_item_with_no_due_date_field_set_is_correctly_no_due_date(load_fixture):
    """Real UDEM finding: an instructor can write a deadline only in free
    text ("entrega tu tarea en tiempo y forma") without ever setting
    Blackboard's own Due Date field on the item. That's a genuinely
    NO_DUE_DATE item, not a parser failure — must not be guessed at."""
    html = load_fixture("course_content_udem_real_structure.html")
    result = _parse(html)

    activity = _by_title(result, "Actividad integradora 2")
    assert activity.due_date is None
    assert activity.due_date_status == DueDateStatus.NO_DUE_DATE


def test_toolbar_buttons_are_excluded_not_logged_as_broken_items(load_fixture):
    html = load_fixture("course_content_udem_real_structure.html")
    result = _parse(html)
    ids = {a.id for a in result}
    assert "refreshMenuLink" not in ids
    assert "courseMapButton" not in ids
