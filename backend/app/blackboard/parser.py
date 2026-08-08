"""HTML -> normalized DTOs. No network, no Playwright, no browser.

This is deliberately the seam between browser automation and data parsing
(Phase 2 requirement #16): PlaywrightBlackboardProvider only ever fetches
`page.content()` and hands the raw HTML string to the functions here. That
means every parsing rule can be exercised with saved fixture HTML in
tests/blackboard/fixtures, without opening a real browser or touching a
real Blackboard instance.

IMPORTANT — selector honesty: Blackboard's DOM differs by version (Ultra vs
Original Experience) and by institution theme, and no real HTML from the
user's Blackboard was available while writing this. Rather than guessing
one fixed set of CSS selectors (and silently returning wrong/empty data
against a real instance), every extraction step tries a list of candidate
strategies in order of specificity and falls back gracefully, logging a
warning when nothing matches instead of raising or inventing a value. When
real HTML samples are available (see ARCHITECTURE.md section 16 checklist),
the candidate lists below are the only thing that should need updating.
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag
from dateutil import parser as dateutil_parser

from app.blackboard.dedupe import IdentitySource, resolve_identity
from app.blackboard.dto import (
    Assignment,
    AssignmentKind,
    AssignmentTimingStatus,
    AttachmentRef,
    Course,
    DueDateStatus,
    FieldStatus,
)

logger = logging.getLogger("blackboard.parser")

# --- selector candidates -------------------------------------------------
# Tried in order; first strategy that yields a non-empty result wins.

COURSE_LINK_SELECTORS = [
    'a[href*="course_id="]',           # Original Experience
    'a[href*="/ultra/courses/"]',      # Ultra
    '[role="listitem"] a[href]',       # generic ARIA list pattern
]

ASSIGNMENT_ITEM_SELECTORS = [
    '[role="listitem"]',
    "li.contentListItem",
    "li[id]",
    "div.contentListItem",
]

ATTACHMENT_HREF_HINTS = (
    "/bbcswebdav/",
    "/webapps/blackboard/execute/content/file",
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".zip",
)

DUE_DATE_PATTERN = re.compile(r"due[^:]*:\s*(.+?)(?:$|\||\n)", re.IGNORECASE)
POINTS_PATTERN = re.compile(r"([\d.]+)\s*(?:points|pts)\b", re.IGNORECASE)
RUBRIC_PATTERN = re.compile(r"rubric", re.IGNORECASE)


def _attr_str(tag: Tag, name: str) -> str | None:
    """BeautifulSoup types attribute values as str | list[str] | None (some
    attributes, like `class`, can be multi-valued). href/id/role are always
    single strings in practice; this normalizes either shape to a plain str
    so the rest of the parser doesn't have to think about it.
    """
    value = tag.get(name)
    if value is None:
        return None
    if isinstance(value, list):
        return " ".join(value)
    return str(value)


def _absolute_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(base_url + "/", href)


def _first_matching(soup: BeautifulSoup, selectors: list[str]) -> list[Tag]:
    for selector in selectors:
        found = soup.select(selector)
        if found:
            return found
    return []


def _course_id_from_href(href: str) -> str | None:
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    if "course_id" in qs and qs["course_id"]:
        return qs["course_id"][0]
    match = re.search(r"/ultra/courses/([^/?#]+)", parsed.path)
    if match:
        return match.group(1)
    return None


def parse_courses_page(html: str, base_url: str) -> list[Course]:
    """Parse a Blackboard "My Courses" / course list page into Course DTOs."""
    soup = BeautifulSoup(html, "html.parser")
    links = _first_matching(soup, COURSE_LINK_SELECTORS)

    if not links:
        logger.warning("parse_courses_page: no course links matched any known selector")
        return []

    seen_ids: set[str] = set()
    courses: list[Course] = []
    for link in links:
        href = _attr_str(link, "href")
        if not href:
            continue
        absolute = _absolute_url(base_url, href)
        course_id = _course_id_from_href(href) or absolute
        if not course_id or course_id in seen_ids:
            continue
        name = link.get_text(strip=True) or _attr_str(link, "aria-label") or course_id
        if not name:
            continue
        seen_ids.add(course_id)
        courses.append(
            Course(
                id=course_id,
                name=name,
                url=absolute or href,
                term=None,  # term is not reliably present on every skin; left unset rather than guessed
                source="playwright",
            )
        )
    return courses


def _parse_due_date(raw_text: str, timezone: str) -> tuple[datetime | None, str | None, DueDateStatus]:
    match = DUE_DATE_PATTERN.search(raw_text)
    if not match:
        return None, None, DueDateStatus.NO_DUE_DATE

    raw_value = match.group(1).strip()
    try:
        tz = ZoneInfo(timezone)
        parsed = dateutil_parser.parse(raw_value, fuzzy=True)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        return parsed.astimezone(ZoneInfo("UTC")), raw_value, DueDateStatus.OK
    except (ValueError, OverflowError):
        logger.warning("Could not parse due date text: %r", raw_value)
        return None, raw_value, DueDateStatus.UNPARSEABLE


def _parse_points(raw_text: str) -> tuple[float | None, FieldStatus]:
    match = POINTS_PATTERN.search(raw_text)
    if not match:
        return None, FieldStatus.NOT_PRESENT
    try:
        return float(match.group(1)), FieldStatus.OK
    except ValueError:
        return None, FieldStatus.DATA_UNAVAILABLE


def _extract_attachments(item: Tag, base_url: str) -> tuple[AttachmentRef, ...]:
    attachments: list[AttachmentRef] = []
    for link in item.find_all("a", href=True):
        href = _attr_str(link, "href")
        if not href:
            continue
        if any(hint in href.lower() for hint in ATTACHMENT_HREF_HINTS):
            filename = link.get_text(strip=True) or href.rsplit("/", 1)[-1]
            file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else None
            attachments.append(
                AttachmentRef(
                    filename=filename or None,
                    url=_absolute_url(base_url, href),
                    file_type=file_type,
                )
            )
    return tuple(attachments)


def _extract_external_links(item: Tag, base_url: str, own_url: str | None) -> tuple[str, ...]:
    links: list[str] = []
    for link in item.find_all("a", href=True):
        href = _attr_str(link, "href")
        if not href:
            continue
        absolute = _absolute_url(base_url, href)
        if not absolute or absolute == own_url:
            continue
        if any(hint in href.lower() for hint in ATTACHMENT_HREF_HINTS):
            continue
        if absolute not in links:
            links.append(absolute)
    return tuple(links)


def _classify_kind(text: str) -> AssignmentKind:
    lowered = text.lower()
    if "quiz" in lowered or "test" in lowered or "exam" in lowered:
        return AssignmentKind.QUIZ
    if "discussion" in lowered:
        return AssignmentKind.DISCUSSION
    if "project" in lowered:
        return AssignmentKind.PROJECT
    if "announcement" in lowered:
        return AssignmentKind.ANNOUNCEMENT
    if "assignment" in lowered or "homework" in lowered:
        return AssignmentKind.ASSIGNMENT
    return AssignmentKind.UNKNOWN


def compute_timing_status(
    due_date: datetime | None,
    due_date_status: DueDateStatus,
    now: datetime,
) -> AssignmentTimingStatus:
    if due_date_status == DueDateStatus.NO_DUE_DATE:
        return AssignmentTimingStatus.NO_DUE_DATE
    if due_date_status == DueDateStatus.UNPARSEABLE or due_date is None:
        return AssignmentTimingStatus.UNKNOWN
    if due_date.date() == now.date():
        return AssignmentTimingStatus.DUE_TODAY
    if due_date < now:
        return AssignmentTimingStatus.OVERDUE
    return AssignmentTimingStatus.UPCOMING


def with_recomputed_timing_status(assignment: Assignment, now: datetime) -> Assignment:
    """Recompute timing_status against the given `now` (e.g. when reading a cached snapshot)."""
    return replace(
        assignment,
        timing_status=compute_timing_status(assignment.due_date, assignment.due_date_status, now),
    )


def parse_assignments_page(
    html: str,
    course_id: str,
    base_url: str,
    timezone: str,
    now: datetime | None = None,
) -> list[Assignment]:
    """Parse a course content/assignments listing page into Assignment DTOs."""
    now = now or datetime.now(ZoneInfo("UTC"))
    soup = BeautifulSoup(html, "html.parser")
    items = _first_matching(soup, ASSIGNMENT_ITEM_SELECTORS)

    if not items:
        logger.warning("parse_assignments_page: no assignment items matched any known selector")
        return []

    assignments: list[Assignment] = []
    for item in items:
        link = item.find("a", href=True)
        if not link:
            logger.warning("Skipping assignment item with no link: %r", _attr_str(item, "id"))
            continue
        assert isinstance(link, Tag)

        title = link.get_text(strip=True) or _attr_str(link, "aria-label")
        if not title:
            logger.warning("Skipping assignment item with no extractable title")
            continue

        href = _attr_str(link, "href")
        if not href:
            logger.warning("Skipping assignment item %r with an empty href", title)
            continue
        url = _absolute_url(base_url, href) or href
        item_text = item.get_text(separator=" ", strip=True)

        due_date, due_date_raw, due_date_status = _parse_due_date(item_text, timezone)
        points, points_status = _parse_points(item_text)
        attachments = _extract_attachments(item, base_url)
        external_links = _extract_external_links(item, base_url, url)
        rubric_ref = "rubric" if RUBRIC_PATTERN.search(item_text) else None

        blackboard_id = _attr_str(item, "id") or _course_id_from_href(href)
        assignment_id, identity_source = resolve_identity(
            course_id=course_id,
            title=title,
            blackboard_id=blackboard_id,
            url=url,
            due_date_raw=due_date_raw,
            points=points,
        )
        if identity_source == IdentitySource.FINGERPRINT:
            logger.info(
                "Assignment %r has no stable Blackboard id or URL; using content fingerprint",
                title,
            )

        assignments.append(
            Assignment(
                id=assignment_id,
                course_id=course_id,
                kind=_classify_kind(title),
                title=title,
                description=None,  # left unset in list view; a detail-page fetch is a later phase
                instructions=None,
                due_date=due_date,
                due_date_raw=due_date_raw,
                due_date_status=due_date_status,
                timezone=timezone,
                points=points,
                points_status=points_status,
                url=url,
                timing_status=compute_timing_status(due_date, due_date_status, now),
                rubric_ref=rubric_ref,
                attachments=attachments,
                external_links=external_links,
                fingerprint=resolve_identity(
                    course_id, title, None, None, due_date_raw, points
                )[0],
                source="playwright",
            )
        )

    return assignments
