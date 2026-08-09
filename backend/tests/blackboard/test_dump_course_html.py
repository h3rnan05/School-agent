"""dump_course_html() — added after get_assignments() came back empty
against a real Original Course View course (real UDEM Blackboard). It
saves the raw HTML plus the URLs actually navigated to/landed on, since
"no assignments found" from OriginalCourseParser could mean either wrong
selectors OR the wrong page entirely — this tells the two apart.

Also covers _resolve_content_entry_url(): confirmed real UDEM finding that
an ORIGINAL Course View course's Ultra outline page embeds its real
content in an <iframe>, invisible to page.content() — so ORIGINAL courses
must start from the classic courseMain URL instead of course.url.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from app.blackboard.config import BlackboardSettings
from app.blackboard.dto import CourseView
from app.blackboard.providers.playwright_provider import PlaywrightBlackboardProvider
from tests.blackboard.factories import make_course


class _FakeLocator:
    def __init__(self, count: int = 0, all_items=None):
        self._count = count
        self._all_items = all_items or []

    def count(self) -> int:
        return self._count

    def all(self):
        return self._all_items


class _FakeLink:
    def __init__(self, text: str, href: str):
        self._text = text
        self._href = href

    def text_content(self, timeout: int | None = None) -> str:
        return self._text

    def get_attribute(self, name: str) -> str | None:
        return self._href if name == "href" else None


class _FakePage:
    def __init__(self, html: str, url: str, links=None):
        self._html = html
        self.url = url
        self._links = links or []
        self.goto_calls: list[str] = []

    def goto(self, url: str) -> None:
        self.goto_calls.append(url)
        self.url = url

    def locator(self, selector: str) -> _FakeLocator:
        if selector == "a":
            return _FakeLocator(all_items=self._links)
        return _FakeLocator(count=0)  # no password field -> not a login page

    def content(self) -> str:
        return self._html

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        pass


def make_settings(tmp_path) -> BlackboardSettings:
    return BlackboardSettings(
        base_url="https://university.blackboard.com",
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


def test_resolve_content_entry_url_for_original_course_bypasses_the_iframe():
    """Confirmed real UDEM markup: the Ultra outline page for an ORIGINAL
    course embeds its content in an iframe pointing here — page.content()
    can't see into it, so this must be the actual navigation target."""
    settings = make_settings(Path("/tmp"))
    provider = PlaywrightBlackboardProvider(settings)
    course = make_course(
        id="_424872_1",
        course_view=CourseView.ORIGINAL,
        url="https://university.blackboard.com/ultra/courses/_424872_1/outline",
    )

    entry_url = provider._resolve_content_entry_url(course)

    assert entry_url == "https://university.blackboard.com/webapps/blackboard/execute/courseMain?course_id=_424872_1"


def test_resolve_content_entry_url_for_non_original_uses_course_url_as_is():
    """No iframe-embedding evidence exists for ULTRA/UNKNOWN course views —
    only the confirmed ORIGINAL case gets special-cased."""
    settings = make_settings(Path("/tmp"))
    provider = PlaywrightBlackboardProvider(settings)

    ultra_course = make_course(id="_1_1", course_view=CourseView.ULTRA, url="https://x/ultra/courses/_1_1/outline")
    assert provider._resolve_content_entry_url(ultra_course) == ultra_course.url

    unknown_course = make_course(id="_2_2", course_view=CourseView.UNKNOWN, url="https://x/ultra/courses/_2_2/outline")
    assert provider._resolve_content_entry_url(unknown_course) == unknown_course.url


def test_dump_course_html_for_original_course_navigates_to_coursemain(tmp_path, monkeypatch):
    course = make_course(
        id="_424872_1",
        course_view=CourseView.ORIGINAL,
        url="https://university.blackboard.com/ultra/courses/_424872_1/outline",
    )
    provider = make_provider_with_cached_course(tmp_path, course)
    expected_entry_url = "https://university.blackboard.com/webapps/blackboard/execute/courseMain?course_id=_424872_1"
    fake_page = _FakePage(html="<html><body>real original-experience content</body></html>", url=expected_entry_url)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "debug_html" / "course_424872.html"
    result = provider.dump_course_html("_424872_1", output_path)

    assert fake_page.goto_calls[0] == expected_entry_url  # bypassed the Ultra outline/iframe entirely
    assert result.html_path == output_path
    assert output_path.read_text(encoding="utf-8") == "<html><body>real original-experience content</body></html>"
    assert result.course_url == course.url  # still reported for reference
    assert result.url_before_content_link == expected_entry_url
    assert result.content_link_followed is None
    assert result.final_url == expected_entry_url


def test_dump_course_html_follows_a_matching_content_link(tmp_path, monkeypatch):
    course = make_course(
        id="_424872_1",
        course_view=CourseView.ORIGINAL,
        url="https://university.blackboard.com/ultra/courses/_424872_1/outline",
    )
    provider = make_provider_with_cached_course(tmp_path, course)
    entry_url = "https://university.blackboard.com/webapps/blackboard/execute/courseMain?course_id=_424872_1"
    content_url = "https://university.blackboard.com/webapps/blackboard/content/listContent.jsp?course_id=_424872_1"
    links = [_FakeLink(text="Course Content", href=content_url)]
    fake_page = _FakePage(html="<html><body>real content listing</body></html>", url=entry_url, links=links)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "course_424872.html"
    result = provider.dump_course_html("_424872_1", output_path)

    assert result.content_link_followed == content_url
    assert result.final_url == content_url
    assert result.url_before_content_link == entry_url  # recorded before following the link


def test_dump_course_html_skips_non_navigable_content_link_instead_of_crashing(tmp_path, monkeypatch):
    """Real UDEM finding: the course menu has an accessibility "skip to
    content" link whose text matches "content" but whose href is just
    "#content" — page.goto("#content") raised a Playwright protocol error.
    A real, followable link further down the list must still be found."""
    course = make_course(
        id="_424872_1",
        course_view=CourseView.ORIGINAL,
        url="https://university.blackboard.com/ultra/courses/_424872_1/outline",
    )
    provider = make_provider_with_cached_course(tmp_path, course)
    entry_url = "https://university.blackboard.com/webapps/blackboard/execute/courseMain?course_id=_424872_1"
    real_content_url = "https://university.blackboard.com/webapps/blackboard/content/listContent.jsp?course_id=_424872_1"
    links = [
        _FakeLink(text="Skip to main content", href="#content"),
        _FakeLink(text="Course Content", href=real_content_url),
    ]
    fake_page = _FakePage(html="<html><body>real content listing</body></html>", url=entry_url, links=links)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "course_424872.html"
    result = provider.dump_course_html("_424872_1", output_path)  # must not raise

    assert result.content_link_followed == real_content_url
    assert "#content" not in fake_page.goto_calls


def test_dump_course_html_follows_extra_link_by_text(tmp_path, monkeypatch):
    """Real UDEM finding: the auto-followed content link lands on the
    course's left-nav menu, not assignments — follow_link_text lets a
    specific content area (e.g. "Assessments") be inspected one level
    deeper without DevTools."""
    course = make_course(
        id="_424872_1",
        course_view=CourseView.ORIGINAL,
        url="https://university.blackboard.com/ultra/courses/_424872_1/outline",
    )
    provider = make_provider_with_cached_course(tmp_path, course)
    entry_url = "https://university.blackboard.com/webapps/blackboard/execute/courseMain?course_id=_424872_1"
    content_url = "https://university.blackboard.com/webapps/blackboard/content/listContent.jsp?course_id=_424872_1"
    assessments_url = "https://university.blackboard.com/webapps/blackboard/content/listContent.jsp?content_id=_999_1"
    links = [
        _FakeLink(text="Course Content", href=content_url),
        _FakeLink(text="Assessments", href=assessments_url),
        _FakeLink(text="Unidad 1", href="https://university.blackboard.com/webapps/blackboard/content/listContent.jsp?content_id=_998_1"),
    ]
    fake_page = _FakePage(html="<html><body>assessments content</body></html>", url=entry_url, links=links)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "course_424872.html"
    result = provider.dump_course_html("_424872_1", output_path, follow_link_text="Assessments")

    assert result.follow_link_text_requested == "Assessments"
    assert result.follow_link_result == assessments_url
    assert result.final_url == assessments_url
    assert fake_page.goto_calls[-1] == assessments_url


def test_dump_course_html_follow_link_text_not_found_reports_none(tmp_path, monkeypatch):
    course = make_course(
        id="_424872_1",
        course_view=CourseView.ORIGINAL,
        url="https://university.blackboard.com/ultra/courses/_424872_1/outline",
    )
    provider = make_provider_with_cached_course(tmp_path, course)
    entry_url = "https://university.blackboard.com/webapps/blackboard/execute/courseMain?course_id=_424872_1"
    content_url = "https://university.blackboard.com/webapps/blackboard/content/listContent.jsp?course_id=_424872_1"
    links = [_FakeLink(text="Course Content", href=content_url)]
    fake_page = _FakePage(html="<html></html>", url=entry_url, links=links)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "course_424872.html"
    result = provider.dump_course_html("_424872_1", output_path, follow_link_text="Nonexistent Area")

    assert result.follow_link_text_requested == "Nonexistent Area"
    assert result.follow_link_result is None
    assert result.final_url == content_url  # stayed on the auto-followed content page


def test_dump_course_html_resolves_relative_content_link_to_absolute(tmp_path, monkeypatch):
    """Real UDEM crash: the course menu's link to "Course Content" itself
    can be a relative href, and page.goto() does NOT resolve relative URLs
    against the current page — it raises "Cannot navigate to invalid URL"
    unless given a full URL. _find_content_link must return an absolute one."""
    course = make_course(
        id="_424872_1",
        course_view=CourseView.ORIGINAL,
        url="https://university.blackboard.com/ultra/courses/_424872_1/outline",
    )
    provider = make_provider_with_cached_course(tmp_path, course)
    entry_url = "https://university.blackboard.com/webapps/blackboard/execute/courseMain?course_id=_424872_1"
    relative_href = "/webapps/blackboard/content/listContent.jsp?course_id=_424872_1"
    links = [_FakeLink(text="Course Content", href=relative_href)]
    fake_page = _FakePage(html="<html><body>content</body></html>", url=entry_url, links=links)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "course_424872.html"
    result = provider.dump_course_html("_424872_1", output_path)

    assert result.content_link_followed == "https://university.blackboard.com" + relative_href
    assert result.content_link_followed in fake_page.goto_calls


def test_dump_course_html_resolves_relative_follow_link_to_absolute(tmp_path, monkeypatch):
    """The exact real crash: --follow "Assessments" found a relative href
    ("/webapps/blackboard/content/listContent.jsp?...") and page.goto()
    on it raised a Playwright protocol error."""
    course = make_course(
        id="_424872_1",
        course_view=CourseView.ORIGINAL,
        url="https://university.blackboard.com/ultra/courses/_424872_1/outline",
    )
    provider = make_provider_with_cached_course(tmp_path, course)
    entry_url = "https://university.blackboard.com/webapps/blackboard/execute/courseMain?course_id=_424872_1"
    content_url = "https://university.blackboard.com/webapps/blackboard/content/listContent.jsp?course_id=_424872_1"
    relative_assessments_href = "/webapps/blackboard/content/listContent.jsp?course_id=_424872_1&content_id=_8713767_1&mode=reset"
    links = [
        _FakeLink(text="Course Content", href=content_url),
        _FakeLink(text="Assessments", href=relative_assessments_href),
    ]
    fake_page = _FakePage(html="<html><body>assessments</body></html>", url=entry_url, links=links)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "course_424872.html"
    result = provider.dump_course_html("_424872_1", output_path, follow_link_text="Assessments")  # must not raise

    expected_absolute = "https://university.blackboard.com" + relative_assessments_href
    assert result.follow_link_result == expected_absolute
    assert result.final_url == expected_absolute
    assert relative_assessments_href not in fake_page.goto_calls  # never goto()'d the bare relative string
