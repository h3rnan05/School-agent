"""Low-level HTML helpers shared by every course-view-specific parser.

Nothing institution- or course-view-specific lives here — just the plumbing
(attribute access, URL resolution, due-date/points/attachment extraction
from a chunk of text) that both OriginalCourseParser and UltraCourseParser
need. No network, no Playwright, no browser: pure functions over strings
and BeautifulSoup Tags, so they're testable with saved fixture HTML.
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

from app.blackboard.dto import (
    Assignment,
    AssignmentKind,
    AssignmentTimingStatus,
    AttachmentRef,
    DueDateStatus,
    FieldStatus,
)

logger = logging.getLogger("blackboard.parsers.common")

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


def attr_str(tag: Tag, name: str) -> str | None:
    """BeautifulSoup types attribute values as str | list[str] | None (some
    attributes, like `class`, can be multi-valued). href/id/role are always
    single strings in practice; this normalizes either shape to a plain str
    so callers don't have to think about it.
    """
    value = tag.get(name)
    if value is None:
        return None
    if isinstance(value, list):
        return " ".join(value)
    return str(value)


def absolute_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(base_url + "/", href)


def first_matching(soup: BeautifulSoup, selectors: list[str]) -> list[Tag]:
    """Tries each selector in order; returns the first non-empty result.

    This is the fallback-chain mechanism every parser here uses instead of
    committing to one fixed selector — see the parsers package docstring.
    """
    for selector in selectors:
        found = soup.select(selector)
        if found:
            return found
    return []


def course_id_from_href(href: str) -> str | None:
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    if "course_id" in qs and qs["course_id"]:
        return qs["course_id"][0]
    match = re.search(r"/ultra/courses/([^/?#]+)", parsed.path)
    if match:
        return match.group(1)
    return None


def parse_due_date(raw_text: str, timezone: str) -> tuple[datetime | None, str | None, DueDateStatus]:
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


def parse_points(raw_text: str) -> tuple[float | None, FieldStatus]:
    match = POINTS_PATTERN.search(raw_text)
    if not match:
        return None, FieldStatus.NOT_PRESENT
    try:
        return float(match.group(1)), FieldStatus.OK
    except ValueError:
        return None, FieldStatus.DATA_UNAVAILABLE


def extract_attachments(item: Tag, base_url: str) -> tuple[AttachmentRef, ...]:
    attachments: list[AttachmentRef] = []
    for link in item.find_all("a", href=True):
        href = attr_str(link, "href")
        if not href:
            continue
        if any(hint in href.lower() for hint in ATTACHMENT_HREF_HINTS):
            filename = link.get_text(strip=True) or href.rsplit("/", 1)[-1]
            file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else None
            attachments.append(
                AttachmentRef(
                    filename=filename or None,
                    url=absolute_url(base_url, href),
                    file_type=file_type,
                )
            )
    return tuple(attachments)


def extract_external_links(item: Tag, base_url: str, own_url: str | None) -> tuple[str, ...]:
    links: list[str] = []
    for link in item.find_all("a", href=True):
        href = attr_str(link, "href")
        if not href:
            continue
        absolute = absolute_url(base_url, href)
        if not absolute or absolute == own_url:
            continue
        if any(hint in href.lower() for hint in ATTACHMENT_HREF_HINTS):
            continue
        if absolute not in links:
            links.append(absolute)
    return tuple(links)


def classify_kind(text: str) -> AssignmentKind:
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
