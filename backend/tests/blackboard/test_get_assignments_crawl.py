"""get_assignments()'s automatic content-area crawl — added after manual
--follow testing confirmed real UDEM course menus mix content-area links
(listContent.jsp+content_id, e.g. "Unidad 1") with tool links
(launchLink.jsp+tool_type=TOOL, e.g. "Discussions") and external links
(a different host entirely, e.g. a library catalog) inside the same
.navPaletteContent menu. Only confirmed content-area links get visited.
"""
from __future__ import annotations

from contextlib import contextmanager

from app.blackboard.config import BlackboardSettings
from app.blackboard.dto import CourseView
from app.blackboard.providers import playwright_provider as pw_module
from app.blackboard.providers.playwright_provider import PlaywrightBlackboardProvider
from tests.blackboard.factories import make_course

BASE_URL = "https://university.blackboard.com"
LANDING_URL = f"{BASE_URL}/webapps/blackboard/execute/courseMain?course_id=_424872_1"
UNIDAD1_URL = f"{BASE_URL}/webapps/blackboard/content/listContent.jsp?course_id=_424872_1&content_id=_111_1"
ASSESSMENTS_URL = f"{BASE_URL}/webapps/blackboard/content/listContent.jsp?course_id=_424872_1&content_id=_222_1"
DISCUSSIONS_URL = f"{BASE_URL}/webapps/blackboard/content/launchLink.jsp?course_id=_424872_1&tool_id=_131_1&tool_type=TOOL"
EXTERNAL_URL = "https://search.ebscohost.com/login.aspx?authtype=guest"

MENU_LINKS = [
    (UNIDAD1_URL, "Unidad 1"),
    (ASSESSMENTS_URL, "Assessments"),
    (DISCUSSIONS_URL, "Discussions"),
    (EXTERNAL_URL, "Biblioteca UDEM"),
]

UNIDAD1_ITEM_HTML = f"""
<li class="clearfix liItem read" id="contentListItem:_999_1">
  <a href="{BASE_URL}/webapps/blackboard/content/listContent.jsp?course_id=_424872_1&content_id=_999_1">Tarea 1</a>
</li>
"""

EMPTY_FOLDER_HTML = '<div class="noItems container-empty">There is no content to display.</div>'


class _FakeLocator:
    def __init__(self, all_items=None, count: int = 0):
        self._all_items = all_items or []
        self._count = count

    def all(self):
        return self._all_items

    def count(self) -> int:
        return self._count


class _FakeLink:
    def __init__(self, href: str, text: str = ""):
        self._href = href
        self._text = text

    def get_attribute(self, name: str) -> str | None:
        return self._href if name == "href" else None

    def text_content(self, timeout: int | None = None) -> str:
        return self._text


class _PageState:
    def __init__(self, html: str, menu_links=None, page_links=None):
        self.html = html
        self.menu_links = menu_links or []
        self.page_links = page_links or []


class _FakeMultiPage:
    """Unlike the single-state fakes in other test files, this returns
    different content/links depending on the current page.url — needed to
    exercise a multi-page crawl instead of a single navigation."""

    def __init__(self, pages: dict[str, _PageState], start_url: str):
        self.url = start_url
        self._pages = pages
        self.goto_calls: list[str] = []

    def goto(self, url: str) -> None:
        self.goto_calls.append(url)
        self.url = url

    def locator(self, selector: str) -> _FakeLocator:
        state = self._pages.get(self.url)
        if state is None:
            return _FakeLocator()
        if selector == ".navPaletteContent a":
            return _FakeLocator(all_items=[_FakeLink(href, text) for href, text in state.menu_links])
        if selector == "a":
            return _FakeLocator(all_items=[_FakeLink(href, text) for href, text in state.page_links])
        return _FakeLocator(count=0)  # no password field -> not a login page

    def content(self) -> str:
        state = self._pages.get(self.url)
        return state.html if state else ""

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        pass


def make_settings(tmp_path) -> BlackboardSettings:
    return BlackboardSettings(
        base_url=BASE_URL,
        timezone="UTC",
        state_dir=tmp_path,
        login_timeout_seconds=60,
        request_timeout_ms=5000,
        max_retries=1,
        headless_for_non_login=True,
        courses_path="/ultra/course",
    )


def make_provider_with_cached_course(tmp_path, course):
    settings = make_settings(tmp_path)
    provider = PlaywrightBlackboardProvider(settings)
    provider._course_cache = {course.id: course}
    return provider


def default_pages() -> dict[str, _PageState]:
    return {
        LANDING_URL: _PageState(html="<html><body>course menu only</body></html>", menu_links=MENU_LINKS),
        UNIDAD1_URL: _PageState(html=UNIDAD1_ITEM_HTML),
        ASSESSMENTS_URL: _PageState(html=EMPTY_FOLDER_HTML),
    }


def test_looks_like_content_area_url(tmp_path):
    provider = make_provider_with_cached_course(tmp_path, make_course())
    assert provider._looks_like_content_area_url(UNIDAD1_URL) is True
    assert provider._looks_like_content_area_url(DISCUSSIONS_URL) is False  # launchLink, tool
    assert provider._looks_like_content_area_url(EXTERNAL_URL) is False  # different host
    assert provider._looks_like_content_area_url(f"{BASE_URL}/webapps/blackboard/content/listContent.jsp") is False  # no content_id


def test_get_assignments_crawls_content_areas_and_skips_tools_and_external(tmp_path, monkeypatch):
    course = make_course(id="_424872_1", course_view=CourseView.ORIGINAL, url=f"{BASE_URL}/ultra/courses/_424872_1/outline")
    provider = make_provider_with_cached_course(tmp_path, course)
    fake_page = _FakeMultiPage(default_pages(), start_url=LANDING_URL)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    result = provider.get_assignments("_424872_1")

    assert [a.title for a in result] == ["Tarea 1"]
    assert UNIDAD1_URL in fake_page.goto_calls
    assert ASSESSMENTS_URL in fake_page.goto_calls
    assert DISCUSSIONS_URL not in fake_page.goto_calls  # tool link, never visited
    assert EXTERNAL_URL not in fake_page.goto_calls  # external link, never visited


def test_get_assignments_dedupes_across_content_areas(tmp_path, monkeypatch):
    """Same assignment id showing up from two content areas (shouldn't
    normally happen, but menus can theoretically link the same area twice)
    must not produce duplicate results."""
    course = make_course(id="_424872_1", course_view=CourseView.ORIGINAL, url=f"{BASE_URL}/ultra/courses/_424872_1/outline")
    provider = make_provider_with_cached_course(tmp_path, course)

    pages = {
        LANDING_URL: _PageState(
            html="<html></html>",
            menu_links=[(UNIDAD1_URL, "Unidad 1"), (ASSESSMENTS_URL, "Unidad 1 (again)")],
        ),
        UNIDAD1_URL: _PageState(html=UNIDAD1_ITEM_HTML),
        ASSESSMENTS_URL: _PageState(html=UNIDAD1_ITEM_HTML),  # same item, same id, on both "areas"
    }
    fake_page = _FakeMultiPage(pages, start_url=LANDING_URL)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    result = provider.get_assignments("_424872_1")

    assert len(result) == 1


def test_get_assignments_respects_max_content_area_pages_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(pw_module, "MAX_CONTENT_AREA_PAGES", 1)

    course = make_course(id="_424872_1", course_view=CourseView.ORIGINAL, url=f"{BASE_URL}/ultra/courses/_424872_1/outline")
    provider = make_provider_with_cached_course(tmp_path, course)
    fake_page = _FakeMultiPage(default_pages(), start_url=LANDING_URL)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    provider.get_assignments("_424872_1")  # must not raise

    visited_content_areas = [u for u in fake_page.goto_calls if u in (UNIDAD1_URL, ASSESSMENTS_URL)]
    assert len(visited_content_areas) == 1
