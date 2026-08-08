"""Covers _looks_like_login_page — the robust, skin-agnostic check that
replaced relying on guessed "logged in" selectors (which failed against
real UDEM Blackboard: the selectors simply didn't match, and the old code
treated that as "login failed" even though the user had genuinely logged
in). No real browser is used here — page.locator()/page.url are faked.
"""
from app.blackboard.config import BlackboardSettings
from app.blackboard.providers.playwright_provider import PlaywrightBlackboardProvider


class _FakeLocator:
    def __init__(self, count: int):
        self._count = count

    def count(self) -> int:
        return self._count


class _FakePage:
    def __init__(self, password_field_count: int = 0, url: str = "https://university.blackboard.com/ultra/course"):
        self._password_field_count = password_field_count
        self.url = url

    def locator(self, selector: str):
        if selector == 'input[type="password"]':
            return _FakeLocator(self._password_field_count)
        return _FakeLocator(0)


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


def make_provider(tmp_path) -> PlaywrightBlackboardProvider:
    return PlaywrightBlackboardProvider(make_settings(tmp_path))


def test_password_field_means_looks_like_login_page(tmp_path):
    provider = make_provider(tmp_path)
    page = _FakePage(password_field_count=1, url="https://university.blackboard.com/ultra/course")
    assert provider._looks_like_login_page(page) is True


def test_authenticated_page_with_no_password_field_is_not_a_login_page(tmp_path):
    provider = make_provider(tmp_path)
    page = _FakePage(password_field_count=0, url="https://university.blackboard.com/ultra/course")
    assert provider._looks_like_login_page(page) is False


def test_sso_url_without_password_field_still_flagged(tmp_path):
    """Covers an intermediate SSO redirect step where the password field
    hasn't rendered yet but the URL already gives it away."""
    provider = make_provider(tmp_path)
    page = _FakePage(password_field_count=0, url="https://mycompany.okta.com/app/blackboard/abc123/sso/saml")
    assert provider._looks_like_login_page(page) is True


def test_locator_error_does_not_crash_the_check(tmp_path):
    """If the page is mid-navigation and locator() raises, the URL check
    must still run instead of blowing up."""
    provider = make_provider(tmp_path)

    class _ExplodingPage:
        url = "https://university.blackboard.com/login/sso"

        def locator(self, selector):
            raise RuntimeError("page is navigating")

    assert provider._looks_like_login_page(_ExplodingPage()) is True
