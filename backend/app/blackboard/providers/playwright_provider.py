"""PlaywrightBlackboardProvider — the real, browser-automation-backed
implementation of BlackboardProvider (ARCHITECTURE.md section 8).

Strictly read-only: this class only ever calls page.goto / page.content /
page.locator(...).all() style read operations. It never calls .click() on
anything that submits a form, never fills in submission text boxes, never
touches grade or settings pages.

Browser automation (this file) is kept separate from HTML parsing
(the parsers/ package) so the parsing rules can be tested with saved
fixtures without a browser. This file's job is only: get a page, get its
HTML, hand it to the right parser for that course's course_view.
"""
from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.blackboard.auth import SessionStore, build_session_handle, wait_for_manual_login
from app.blackboard.browser import ManagedBrowser, with_retries
from app.blackboard.changes import diff_assignments  # re-exported for CLI convenience
from app.blackboard.config import BlackboardSettings
from app.blackboard.dto import Assignment, Course, CourseView, UpcomingAssignments
from app.blackboard.exceptions import (
    BlackboardUnavailableError,
    CourseUnavailableError,
    LoginFailedError,
    NoSessionError,
    SessionExpiredError,
)
from app.blackboard.parsers import AssignmentParser, CourseListParser, with_recomputed_timing_status
from app.blackboard.provider import BlackboardProvider, ProviderHealth, SessionHandle

logger = logging.getLogger("blackboard.provider.playwright")


@dataclass(frozen=True)
class CourseDumpResult:
    """Return value of PlaywrightBlackboardProvider.dump_course_html —
    diagnostic info, not part of any BlackboardProvider-facing DTO.
    """

    html_path: Path
    course_url: str
    url_before_content_link: str
    content_link_followed: str | None
    final_url: str

# Candidate selectors for detecting the logged-in user's DISPLAY NAME only.
# This is best-effort and cosmetic (used for the "Logged in as: ..." message
# and nothing else) — see the module docstring on _looks_like_login_page for
# why actual authentication checks don't depend on this list matching.
USERNAME_SELECTORS = [
    '[data-testid="global-nav-user-menu"]',
    "#userDropdown",
    'a[href*="/webapps/portal/execute/tabs/tabAction"] span',
    '[role="banner"] [aria-label*="account" i]',
]

# URL fragments that show up across common SSO/IdP flows (Okta, Azure AD,
# Shibboleth/ADFS, Blackboard's own login page) — used as a fallback signal
# in _looks_like_login_page when there's no password field on the page
# (e.g. an intermediate SSO redirect step).
LOGIN_PAGE_URL_HINTS = (
    "/login",
    "/auth/",
    "/idp/",
    "/adfs/",
    "/sso",
    "okta.com",
    "login.microsoftonline.com",
    "shibboleth",
)

# Candidate link text patterns for finding a course's assignment/content area.
CONTENT_LINK_PATTERN = re.compile(r"assignments?|content|coursework", re.IGNORECASE)

__all__ = ["CourseDumpResult", "PlaywrightBlackboardProvider", "diff_assignments"]


class PlaywrightBlackboardProvider(BlackboardProvider):
    def __init__(self, settings: BlackboardSettings):
        self._settings = settings
        self._session_store = SessionStore(settings)
        self._course_cache: dict[str, Course] | None = None
        self._course_list_parser = CourseListParser()
        self._assignment_parser = AssignmentParser()

    # -- session -----------------------------------------------------
    def login(self) -> SessionHandle:
        with ManagedBrowser(self._settings, headless=False) as browser:
            page = browser.new_page()
            try:
                page.goto(self._settings.base_url)
            except Exception as exc:  # noqa: BLE001
                raise BlackboardUnavailableError(f"Could not open {self._settings.base_url}") from exc

            wait_for_manual_login(page, self._settings.base_url, self._settings.login_timeout_seconds)

            # The user's manual ENTER confirmation above is the actual trust
            # boundary — this check is a robust *negative* signal (password
            # field / login-like URL still present) used only to catch a
            # clearly-failed attempt, never a *positive* one we'd need
            # institution-specific selectors to get right.
            if self._looks_like_login_page(page):
                raise LoginFailedError(
                    "This still looks like a login page (found a password field, or "
                    "the URL still looks like a login/SSO page) even after you "
                    "confirmed. Make sure the browser actually reached your Blackboard "
                    "homepage before pressing ENTER, then run `login` again."
                )

            # Best-effort only, purely cosmetic (see USERNAME_SELECTORS) — a
            # miss here must never stop the session from being saved.
            username = self._detect_username(page)

            with tempfile.TemporaryDirectory() as tmp:
                plaintext_path = Path(tmp) / "storage_state.json"
                browser.save_storage_state(plaintext_path)
                self._session_store.save_plaintext_state(plaintext_path)

            if username:
                logger.info("Login confirmed for %s; session saved (encrypted)", username)
            else:
                logger.info(
                    "Login confirmed; session saved (encrypted). Could not detect a "
                    "display name on the page — that's cosmetic only and doesn't "
                    "affect anything else."
                )
            return build_session_handle(username)

    def is_session_valid(self) -> bool:
        if not self._session_store.exists():
            return False
        try:
            with self._authenticated_browser() as (browser, page):
                page.goto(self._settings.base_url)
                return not self._looks_like_login_page(page)
        except (BlackboardUnavailableError, NoSessionError):
            return False

    def get_current_user(self) -> str | None:
        """Best-effort display name for the currently logged-in user — NOT
        the same check as is_session_valid()/_assert_logged_in(), which use
        the more robust _looks_like_login_page() heuristic instead. A miss
        here just means the greeting is generic, not that the session is bad.
        """
        if not self._session_store.exists():
            raise NoSessionError("No persisted Blackboard session found. Run `blackboard login` first.")

        with self._authenticated_browser() as (browser, page):
            try:
                page.goto(self._settings.base_url)
            except Exception as exc:  # noqa: BLE001
                raise BlackboardUnavailableError(f"Could not reach {self._settings.base_url}") from exc
            return self._detect_username(page)

    # -- read-only data ------------------------------------------------
    def get_courses(self) -> list[Course]:
        def _fetch() -> list[Course]:
            with self._authenticated_browser() as (browser, page):
                page.goto(self._settings.courses_list_url)
                self._assert_logged_in(page)
                self._wait_for_render(page)
                html = page.content()
                return self._course_list_parser.parse(html, self._settings.base_url)

        courses = with_retries(_fetch, self._settings.max_retries, "get_courses")
        self._course_cache = {c.id: c for c in courses}
        return courses

    def get_assignments(self, course_id: str) -> list[Assignment]:
        course = self._resolve_course(course_id)

        def _fetch() -> list[Assignment]:
            with self._authenticated_browser() as (browser, page):
                page.goto(self._resolve_content_entry_url(course))
                self._assert_logged_in(page)
                self._wait_for_render(page)

                content_href = self._find_content_link(page)
                if content_href:
                    page.goto(content_href)
                    self._wait_for_render(page)

                html = page.content()
                return self._assignment_parser.parse(
                    html,
                    course=course,
                    base_url=self._settings.base_url,
                    timezone=self._settings.timezone,
                )

        return with_retries(_fetch, self._settings.max_retries, f"get_assignments({course_id})")

    def get_upcoming_assignments(
        self,
        days: int = 7,
        include_overdue: bool = False,
        include_no_due_date: bool = False,
    ) -> UpcomingAssignments:
        all_assignments: list[Assignment] = []
        for course in self.get_courses():
            all_assignments.extend(self.get_assignments(course.id))
        return bucket_assignments(
            all_assignments,
            days=days,
            include_overdue=include_overdue,
            include_no_due_date=include_no_due_date,
        )

    def health_check(self) -> ProviderHealth:
        try:
            ok = self.is_session_valid()
            message = "session valid" if ok else "no valid session"
        except BlackboardUnavailableError as exc:
            ok, message = False, str(exc)
        return ProviderHealth(ok=ok, message=message, checked_at=datetime.now(timezone.utc))

    # -- debug tooling (Playwright-specific, not part of BlackboardProvider) --
    def dump_courses_html(self, output_path: Path) -> Path:
        """Saves the raw HTML of the course list page to disk, read-only,
        using the already-saved session (no new login needed).

        Exists because the real selector work for a new institution can't
        happen from guesses alone (see parsers/DOM_NOTES.md) — this gives a
        way to hand over real markup without needing DevTools knowledge or
        ever sharing login/session data, which never touches this file.
        """
        with self._authenticated_browser() as (browser, page):
            page.goto(self._settings.courses_list_url)
            self._assert_logged_in(page)
            self._wait_for_render(page)
            html = page.content()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def dump_course_html(self, course_id: str, output_path: Path) -> CourseDumpResult:
        """Saves the raw HTML of a single course's content page to disk,
        the same way dump_courses_html() does for the course list.

        Added after get_assignments() came back empty against a real
        Original Course View course accessed through Ultra's course outline
        route — need to see what's actually on that page (and whether
        Blackboard redirected somewhere else) to fix OriginalCourseParser's
        selectors, or _find_content_link's link-following, with evidence.
        """
        course = self._resolve_course(course_id)

        with self._authenticated_browser() as (browser, page):
            page.goto(self._resolve_content_entry_url(course))
            self._assert_logged_in(page)
            self._wait_for_render(page)
            url_before_content_link = page.url

            content_href = self._find_content_link(page)
            if content_href:
                page.goto(content_href)
                self._wait_for_render(page)

            html = page.content()
            final_url = page.url

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return CourseDumpResult(
            html_path=output_path,
            course_url=course.url,
            url_before_content_link=url_before_content_link,
            content_link_followed=content_href,
            final_url=final_url,
        )

    # -- internals -----------------------------------------------------
    def _authenticated_browser(self):
        plaintext_dir = tempfile.TemporaryDirectory()
        plaintext_path = self._session_store.decrypt_to(Path(plaintext_dir.name) / "storage_state.json")
        browser = ManagedBrowser(self._settings, headless=self._settings.headless_for_non_login, storage_state=plaintext_path)

        class _Ctx:
            def __enter__(_self):
                browser.__enter__()
                page = browser.new_page()
                return browser, page

            def __exit__(_self, exc_type, exc, tb):
                browser.__exit__(exc_type, exc, tb)
                plaintext_dir.cleanup()

        return _Ctx()

    def _detect_username(self, page) -> str | None:
        for selector in USERNAME_SELECTORS:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0:
                    text = locator.text_content(timeout=2000)
                    if text and text.strip():
                        return text.strip()
            except Exception:  # noqa: BLE001 - selector may legitimately not exist on this skin
                continue
        return None

    def _assert_logged_in(self, page) -> None:
        if self._looks_like_login_page(page):
            raise SessionExpiredError(
                "Blackboard appears to have redirected to a login page. Run `blackboard login` again."
            )

    def _looks_like_login_page(self, page) -> bool:
        """Robust, skin-agnostic "are we logged out" check: a visible
        password field is a near-universal signal of a login form, whether
        it's Blackboard's own login, Okta, Azure AD, or Shibboleth — unlike
        _detect_username, this doesn't depend on guessing an institution's
        specific "logged in" markup.
        """
        try:
            if page.locator('input[type="password"]').count() > 0:
                return True
        except Exception:  # noqa: BLE001 - page may be mid-navigation
            pass
        url = (page.url or "").lower()
        return any(hint in url for hint in LOGIN_PAGE_URL_HINTS)

    def _wait_for_render(self, page) -> None:
        """Blackboard Ultra pages are React SPAs: the initial page load
        fires before course/assignment data has actually been fetched and
        rendered into the DOM. Grabbing page.content() right after goto()
        can capture an empty shell rather than real content. This waits
        (best-effort — never raises) for network activity to settle before
        any page.content() call, giving the app time to render.
        """
        try:
            page.wait_for_load_state("networkidle", timeout=self._settings.request_timeout_ms)
        except Exception:  # noqa: BLE001 - best-effort only; proceed with whatever rendered so far
            logger.debug("networkidle wait did not complete; proceeding with current page state")

    def _resolve_content_entry_url(self, course: Course) -> str:
        """Where to start navigating to find a course's actual content.

        Confirmed real UDEM finding: for an ORIGINAL Course View course,
        the Ultra outline page (course.url) embeds the real content inside
        an <iframe src="…/webapps/blackboard/execute/courseMain?course_id=
        …">, NOT as part of the outer page — page.content() can't see into
        a same-origin iframe's own document from the parent page at all,
        which is exactly why get_assignments() came back with "no items
        matched" against a real course. Navigating straight to that
        confirmed URL pattern, instead of the Ultra wrapper, gets past the
        iframe boundary entirely.
        """
        if course.course_view == CourseView.ORIGINAL:
            return f"{self._settings.base_url}/webapps/blackboard/execute/courseMain?course_id={course.id}"
        return course.url

    def _find_content_link(self, page) -> str | None:
        try:
            links = page.locator("a").all()
        except Exception:  # noqa: BLE001
            return None
        for link in links:
            try:
                text = link.text_content(timeout=1000) or ""
            except Exception:  # noqa: BLE001
                continue
            if CONTENT_LINK_PATTERN.search(text):
                href = link.get_attribute("href")
                if href:
                    return href
        return None

    def _resolve_course(self, course_id: str) -> Course:
        if self._course_cache is None or course_id not in self._course_cache:
            self.get_courses()
        if self._course_cache is None or course_id not in self._course_cache:
            raise CourseUnavailableError(f"Course {course_id!r} was not found in your course list")
        return self._course_cache[course_id]


def bucket_assignments(
    assignments: list[Assignment],
    days: int,
    include_overdue: bool,
    include_no_due_date: bool,
) -> UpcomingAssignments:
    """Pure helper (no I/O) so it can be unit tested without a provider."""
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=days)

    upcoming = []
    overdue = []
    no_due_date = []

    for assignment in assignments:
        recomputed = with_recomputed_timing_status(assignment, now)
        if recomputed.due_date_status.value == "NO_DUE_DATE":
            if include_no_due_date:
                no_due_date.append(recomputed)
            continue
        if recomputed.due_date is None:
            continue  # UNPARSEABLE — never guessed into a bucket
        if now <= recomputed.due_date <= window_end:
            upcoming.append(recomputed)
        elif recomputed.due_date < now and include_overdue:
            overdue.append(recomputed)

    return UpcomingAssignments(
        upcoming=tuple(upcoming),
        overdue=tuple(overdue),
        no_due_date=tuple(no_due_date),
    )
