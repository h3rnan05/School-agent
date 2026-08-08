"""dump_course_html() — added after get_assignments() came back empty
against a real Original Course View course (real UDEM Blackboard). It
saves the raw HTML plus the URLs actually navigated to/landed on, since
"no assignments found" from OriginalCourseParser could mean either wrong
selectors OR the wrong page entirely — this tells the two apart.
"""
from __future__ import annotations

from contextlib import contextmanager

from app.blackboard.config import BlackboardSettings
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

    def goto(self, url: str) -> None:
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


def test_dump_course_html_without_a_content_link(tmp_path, monkeypatch):
    course = make_course(id="_424872_1", url="https://university.blackboard.com/ultra/courses/_424872_1/outline")
    provider = make_provider_with_cached_course(tmp_path, course)
    fake_page = _FakePage(html="<html><body>course outline, no content link here</body></html>", url=course.url)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "debug_html" / "course_424872.html"
    result = provider.dump_course_html("_424872_1", output_path)

    assert result.html_path == output_path
    assert output_path.read_text(encoding="utf-8") == "<html><body>course outline, no content link here</body></html>"
    assert result.course_url == course.url
    assert result.url_before_content_link == course.url
    assert result.content_link_followed is None
    assert result.final_url == course.url  # never navigated anywhere else


def test_dump_course_html_follows_a_matching_content_link(tmp_path, monkeypatch):
    course = make_course(id="_424872_1", url="https://university.blackboard.com/ultra/courses/_424872_1/outline")
    provider = make_provider_with_cached_course(tmp_path, course)
    content_url = "https://university.blackboard.com/ultra/courses/_424872_1/cl/outline"
    links = [_FakeLink(text="Course Content", href=content_url)]
    fake_page = _FakePage(html="<html><body>real content listing</body></html>", url=course.url, links=links)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "course_424872.html"
    result = provider.dump_course_html("_424872_1", output_path)

    assert result.content_link_followed == content_url
    assert result.final_url == content_url
    assert result.url_before_content_link == course.url  # recorded before following the link
