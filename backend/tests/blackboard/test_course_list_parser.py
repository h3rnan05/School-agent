from app.blackboard.dto import CourseView
from app.blackboard.parsers import CourseListParser

BASE_URL = "https://university.blackboard.com"


def _by_id(courses, course_id):
    return next(c for c in courses if c.id == course_id)


def test_detects_course_view_and_instructor_per_card(load_fixture):
    html = load_fixture("course_list_ultra_mixed.html")
    courses = CourseListParser().parse(html, BASE_URL)

    assert len(courses) == 3

    original = _by_id(courses, "_98765_1")
    assert original.name == "FINC 301 - Corporate Finance"
    assert original.course_view == CourseView.ORIGINAL
    assert original.instructor == "Dr. Maria Gonzalez"

    ultra = _by_id(courses, "_98766_1")
    assert ultra.course_view == CourseView.ULTRA
    assert ultra.instructor == "Dr. Carlos Ruiz"


def test_course_view_is_unknown_when_no_label_present(load_fixture):
    html = load_fixture("course_list_ultra_mixed.html")
    courses = CourseListParser().parse(html, BASE_URL)

    seminar = _by_id(courses, "_98767_1")
    assert seminar.course_view == CourseView.UNKNOWN  # never guessed
    assert seminar.instructor is None


def test_course_view_never_assumed_from_experience_alone(load_fixture):
    """The institution's base navigation being Ultra Experience must not
    make every course ULTRA — Phase 2.1's core UDEM finding."""
    html = load_fixture("course_list_ultra_mixed.html")
    courses = CourseListParser().parse(html, BASE_URL)
    views = {c.course_view for c in courses}
    assert CourseView.ORIGINAL in views
    assert CourseView.ULTRA in views


def test_falls_back_to_bare_links_when_no_card_containers(load_fixture):
    """Original Experience's flatter "My Courses" markup has no card
    containers at all; CourseListParser must still find the courses,
    just without course_view/instructor context."""
    html = load_fixture("courses_original.html")
    courses = CourseListParser().parse(html, BASE_URL)

    assert len(courses) == 2
    for course in courses:
        assert course.course_view == CourseView.UNKNOWN
        assert course.instructor is None


def test_role_listitem_cards_without_testid_still_parse(load_fixture):
    """Exercises the CARD_SELECTORS fallback chain past data-testid, down
    to plain [role="listitem"] containers with no course-view label."""
    html = load_fixture("courses_ultra.html")
    courses = CourseListParser().parse(html, BASE_URL)

    assert len(courses) == 2
    for course in courses:
        assert course.course_view == CourseView.UNKNOWN
        assert course.instructor is None


def test_duplicate_courses_are_not_repeated(load_fixture):
    html = load_fixture("course_list_ultra_mixed.html")
    courses = CourseListParser().parse(html, BASE_URL)
    ids = [c.id for c in courses]
    assert len(ids) == len(set(ids))


def test_missing_course_links_returns_empty_list_not_error(load_fixture):
    html = load_fixture("courses_empty.html")
    courses = CourseListParser().parse(html, BASE_URL)
    assert courses == []


def test_parses_real_udem_card_structure(load_fixture):
    """Modeled on the actual markup the user shared from DevTools
    (Phase 2.1): article[data-course-id] cards, a.course-title link with
    an h4.js-course-title-element name and a .course-type span, and a
    [class*="course_username"] instructor span."""
    html = load_fixture("course_list_udem_real_structure.html")
    courses = CourseListParser().parse(html, BASE_URL)

    assert len(courses) == 2

    finance = _by_id(courses, "_555111_1")
    assert finance.name == "FINC 301 - Corporate Finance"
    assert finance.instructor == "Dr. Maria Gonzalez"
    assert finance.url == f"{BASE_URL}/ultra/courses/_555111_1/outline"
    # course_view text is a best-effort guess pending confirmation — see
    # DOM_NOTES.md — so this only checks it's read from the real card
    # rather than falling back to UNKNOWN, not the specific value.
    assert finance.course_view in (CourseView.ORIGINAL, CourseView.ULTRA)


def test_data_course_id_attribute_is_preferred_over_url_derived_id(load_fixture):
    """Blackboard's own data-course-id is more trustworthy than anything
    parsed out of a URL — confirmed present on real UDEM cards."""
    html = load_fixture("course_list_udem_real_structure.html")
    courses = CourseListParser().parse(html, BASE_URL)
    ids = {c.id for c in courses}
    assert ids == {"_555111_1", "_555112_1"}
