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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.blackboard.auth import (
    SessionStore,
    build_session_handle,
    require_username_or_fail,
    wait_for_manual_login,
)
from app.blackboard.browser import ManagedBrowser, with_retries
from app.blackboard.changes import diff_assignments  # re-exported for CLI convenience
from app.blackboard.config import BlackboardSettings
from app.blackboard.dto import Assignment, Course, UpcomingAssignments
from app.blackboard.exceptions import (
    BlackboardUnavailableError,
    CourseUnavailableError,
    NoSessionError,
    SessionExpiredError,
)
from app.blackboard.parsers import AssignmentParser, CourseListParser, with_recomputed_timing_status
from app.blackboard.provider import BlackboardProvider, ProviderHealth, SessionHandle

logger = logging.getLogger("blackboard.provider.playwright")

# Candidate selectors for detecting the logged-in username. Tried in order;
# see parsers/course_list.py's module docstring for why this is a fallback list rather
# than a single fixed selector.
USERNAME_SELECTORS = [
    '[data-testid="global-nav-user-menu"]',
    "#userDropdown",
    'a[href*="/webapps/portal/execute/tabs/tabAction"] span',
    '[role="banner"] [aria-label*="account" i]',
]

# Candidate link text patterns for finding a course's assignment/content area.
CONTENT_LINK_PATTERN = re.compile(r"assignments?|content|coursework", re.IGNORECASE)

__all__ = ["PlaywrightBlackboardProvider", "diff_assignments"]


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

            username = self._detect_username(page)
            username = require_username_or_fail(username)

            with tempfile.TemporaryDirectory() as tmp:
                plaintext_path = Path(tmp) / "storage_state.json"
                browser.save_storage_state(plaintext_path)
                self._session_store.save_plaintext_state(plaintext_path)

            logger.info("Login successful for %s; session saved (encrypted)", username)
            return build_session_handle(username)

    def is_session_valid(self) -> bool:
        try:
            return self.get_current_user() is not None
        except NoSessionError:
            return False

    def get_current_user(self) -> str | None:
        if not self._session_store.exists():
            raise NoSessionError("No persisted Blackboard session found. Run `blackboard login` first.")

        with self._authenticated_browser() as (browser, page):
            try:
                page.goto(self._settings.base_url)
            except Exception as exc:  # noqa: BLE001
                raise BlackboardUnavailableError(f"Could not reach {self._settings.base_url}") from exc
            username = self._detect_username(page)
            if username is None:
                logger.info("Session appears expired: no logged-in user detected")
            return username

    # -- read-only data ------------------------------------------------
    def get_courses(self) -> list[Course]:
        def _fetch() -> list[Course]:
            with self._authenticated_browser() as (browser, page):
                page.goto(self._settings.courses_list_url)
                self._assert_logged_in(page)
                html = page.content()
                return self._course_list_parser.parse(html, self._settings.base_url)

        courses = with_retries(_fetch, self._settings.max_retries, "get_courses")
        self._course_cache = {c.id: c for c in courses}
        return courses

    def get_assignments(self, course_id: str) -> list[Assignment]:
        course = self._resolve_course(course_id)

        def _fetch() -> list[Assignment]:
            with self._authenticated_browser() as (browser, page):
                page.goto(course.url)
                self._assert_logged_in(page)

                content_href = self._find_content_link(page)
                if content_href:
                    page.goto(content_href)

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
        if self._detect_username(page) is None:
            raise SessionExpiredError(
                "Blackboard did not recognize the session as logged in. Run `blackboard login` again."
            )

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
