from app.blackboard.parser import parse_courses_page

BASE_URL = "https://university.blackboard.com"


def test_parses_original_experience_courses(load_fixture):
    html = load_fixture("courses_original.html")
    courses = parse_courses_page(html, BASE_URL)

    assert len(courses) == 2  # the third <li> is a duplicate of the first
    ids = {c.id for c in courses}
    assert ids == {"_12345_1", "_67890_1"}

    finance = next(c for c in courses if c.id == "_12345_1")
    assert finance.name == "FINANCE 301 - Corporate Finance"
    assert finance.url.startswith(BASE_URL)
    assert finance.source == "playwright"


def test_parses_ultra_courses(load_fixture):
    html = load_fixture("courses_ultra.html")
    courses = parse_courses_page(html, BASE_URL)

    assert len(courses) == 2
    ids = {c.id for c in courses}
    assert ids == {"_11111_1", "_22222_1"}


def test_duplicate_courses_are_not_repeated(load_fixture):
    html = load_fixture("courses_original.html")
    courses = parse_courses_page(html, BASE_URL)
    ids = [c.id for c in courses]
    assert len(ids) == len(set(ids))


def test_missing_course_links_returns_empty_list_not_error(load_fixture):
    html = load_fixture("courses_empty.html")
    courses = parse_courses_page(html, BASE_URL)
    assert courses == []
