"""dump_courses_html is a Playwright-specific debug helper (not part of
BlackboardProvider) added after real UDEM Blackboard came back with no
courses detected — it lets real page markup be captured and shared without
DevTools knowledge, and without ever touching login/session data.
"""
from contextlib import contextmanager

from app.blackboard.config import BlackboardSettings
from app.blackboard.providers.playwright_provider import PlaywrightBlackboardProvider


class _FakeLocator:
    def count(self) -> int:
        return 0  # no password field -> not a login page


class _FakePage:
    def __init__(self, html: str):
        self._html = html
        self.url = "https://university.blackboard.com/ultra/course"

    def goto(self, url: str) -> None:
        pass

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator()

    def content(self) -> str:
        return self._html


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


def test_dump_courses_html_writes_real_page_content(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    provider = PlaywrightBlackboardProvider(settings)
    fake_page = _FakePage(html="<html><body>real course cards here</body></html>")

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "debug_html" / "courses_page.html"
    result = provider.dump_courses_html(output_path)

    assert result == output_path
    assert output_path.read_text(encoding="utf-8") == "<html><body>real course cards here</body></html>"


def test_dump_courses_html_creates_parent_directory(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    provider = PlaywrightBlackboardProvider(settings)
    fake_page = _FakePage(html="<html></html>")

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "nested" / "dir" / "courses_page.html"
    assert not output_path.parent.exists()

    provider.dump_courses_html(output_path)

    assert output_path.exists()
