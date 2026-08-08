from app.blackboard.dto import CourseView
from app.blackboard.parsers import CourseListParser
from app.blackboard.parsers.course_list import _is_navigable_url

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
    [class*="course_username"] instructor span. course_view text
    ("Original Course View") was confirmed correct against a real run."""
    html = load_fixture("course_list_udem_real_structure.html")
    courses = CourseListParser().parse(html, BASE_URL)

    assert len(courses) == 2  # the 3rd card (no data-course-id) is filtered out

    finance = _by_id(courses, "_555111_1")
    assert finance.name == "FINC 301 - Corporate Finance"
    assert finance.instructor == "Dr. Maria Gonzalez"
    assert finance.course_view == CourseView.ORIGINAL


def test_data_course_id_attribute_is_preferred_over_url_derived_id(load_fixture):
    """Blackboard's own data-course-id is more trustworthy than anything
    parsed out of a URL — confirmed present on real UDEM cards."""
    html = load_fixture("course_list_udem_real_structure.html")
    courses = CourseListParser().parse(html, BASE_URL)
    ids = {c.id for c in courses}
    assert ids == {"_555111_1", "_555112_1"}


def test_javascript_void_href_gets_a_reconstructed_url(load_fixture):
    """Confirmed real UDEM behavior: a.course-title's href is
    "javascript:void(0);" (a JS click handler), not a usable URL. The
    course_id is still known from data-course-id, so a working Ultra
    course URL is reconstructed instead of saving the useless href."""
    html = load_fixture("course_list_udem_real_structure.html")
    courses = CourseListParser().parse(html, BASE_URL)

    finance = _by_id(courses, "_555111_1")
    assert finance.url == f"{BASE_URL}/ultra/courses/_555111_1/outline"
    assert "javascript:" not in finance.url


def test_navigable_href_is_still_used_as_is(load_fixture):
    """When a card DOES have a real href, it's used directly rather than
    always reconstructing one — the reconstruction is a fallback, not the
    default."""
    html = load_fixture("course_list_udem_real_structure.html")
    courses = CourseListParser().parse(html, BASE_URL)

    ml_course = _by_id(courses, "_555112_1")
    assert ml_course.url == f"{BASE_URL}/ultra/courses/_555112_1/outline"


def test_card_without_data_course_id_is_filtered_out(load_fixture):
    """A card sharing the same markup but with no data-course-id and a
    javascript: href (the extra "Browse Catalog"-style tile seen in a real
    run) isn't a real course — must be dropped, not turned into a garbage
    entry keyed by "javascript:void(0);"."""
    html = load_fixture("course_list_udem_real_structure.html")
    courses = CourseListParser().parse(html, BASE_URL)

    names = {c.name for c in courses}
    assert "Browse Catalog" not in names
    assert all("javascript:" not in c.id for c in courses)


def test_is_navigable_url():
    assert _is_navigable_url("https://university.blackboard.com/ultra/courses/_1_1/outline") is True
    assert _is_navigable_url("/ultra/courses/_1_1/outline") is True
    assert _is_navigable_url("javascript:void(0);") is False
    assert _is_navigable_url("JAVASCRIPT:void(0)") is False  # case-insensitive
    assert _is_navigable_url("#") is False
    assert _is_navigable_url("") is False
