"""dump_url_html() — generic same-host page dump, added to inspect a
specific item's detail page (e.g. a real Blackboard Assignment's
uploadAssignment URL) without needing a dedicated method per page type.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from app.blackboard.config import BlackboardSettings
from app.blackboard.providers.playwright_provider import PlaywrightBlackboardProvider


class _FakeLocator:
    def count(self) -> int:
        return 0  # no password field -> not a login page


class _FakePage:
    def __init__(self, html: str, url: str):
        self._html = html
        self.url = url

    def goto(self, url: str) -> None:
        self.url = url

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator()

    def content(self) -> str:
        return self._html

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        pass


def make_settings(tmp_path) -> BlackboardSettings:
    return BlackboardSettings(
        base_url="https://cursos-udem.blackboard.com",
        timezone="UTC",
        state_dir=tmp_path,
        login_timeout_seconds=60,
        request_timeout_ms=5000,
        max_retries=1,
        headless_for_non_login=True,
        courses_path="/ultra/course",
    )


def test_dump_url_html_saves_content(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    provider = PlaywrightBlackboardProvider(settings)
    url = "https://cursos-udem.blackboard.com/webapps/assignment/uploadAssignment?content_id=_1_1&course_id=_2_1"
    fake_page = _FakePage(html="<html><body>assignment detail</body></html>", url=url)

    @contextmanager
    def fake_authenticated_browser():
        yield (None, fake_page)

    monkeypatch.setattr(provider, "_authenticated_browser", fake_authenticated_browser)

    output_path = tmp_path / "debug_html" / "url_dump.html"
    result = provider.dump_url_html(url, output_path)

    assert result == output_path
    assert output_path.read_text(encoding="utf-8") == "<html><body>assignment detail</body></html>"


def test_dump_url_html_refuses_a_different_host(tmp_path):
    settings = make_settings(tmp_path)
    provider = PlaywrightBlackboardProvider(settings)

    with pytest.raises(ValueError, match="does not match"):
        provider.dump_url_html("https://attacker.example.com/steal", tmp_path / "out.html")
