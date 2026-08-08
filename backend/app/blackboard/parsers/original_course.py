"""OriginalCourseParser — parses assignment/content listings for a course
running Blackboard's Original Course View (regardless of whether the
institution's overall navigation is Original Experience or Ultra
Experience — Phase 2.1 confirmed UDEM mixes both).

Phase 2.1 finding (real UDEM run): a real course's content page rendered
its persistent left-hand COURSE MENU (Home Page, Announcements, Discussions,
My Grades, custom instructor-named areas like "Unidad 1", "Assessments",
etc.) as `<li id="paletteItem:_XXX_1">` elements — Blackboard's own
internal name for course-menu items ("palette"). The old, broader
`li[id]` selector matched those too, producing fake "assignments" with no
due dates that were actually just navigation entries. Those are now
explicitly excluded (see NON_CONTENT_ID_PREFIXES) rather than treated as
content — an empty result on a menu/palette page is the honest, correct
answer, not a selector failure.

The real assignments/graded items are one level deeper, inside a specific
content area (e.g. clicking "Unidad 1" or "Assessments") — that page's
structure isn't confirmed yet. This parser's item-selector candidates are
otherwise unchanged from Phase 2, validated only against synthetic
fixtures. See parsers/DOM_NOTES.md and backend/README.md.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.blackboard.dedupe import IdentitySource, resolve_identity
from app.blackboard.dto import Assignment
from app.blackboard.parsers.common import (
    RUBRIC_PATTERN,
    absolute_url,
    attr_str,
    classify_kind,
    compute_timing_status,
    course_id_from_href,
    extract_attachments,
    extract_external_links,
    first_matching,
    parse_due_date,
    parse_points,
)

logger = logging.getLogger("blackboard.parsers.original_course")

ASSIGNMENT_ITEM_SELECTORS = [
    '[role="listitem"]',
    "li.contentListItem",
    "li[id]",
    "div.contentListItem",
]

# Confirmed real UDEM markup: the persistent course (left-nav) menu renders
# each entry as an element with an id starting with "paletteItem:" —
# Blackboard's internal name for these. They're never assignments/content,
# regardless of which broader selector above happens to also match them.
NON_CONTENT_ID_PREFIXES = ("paletteitem:",)


def _is_menu_item(item: Tag) -> bool:
    item_id = (attr_str(item, "id") or "").lower()
    return any(item_id.startswith(prefix) for prefix in NON_CONTENT_ID_PREFIXES)


class OriginalCourseParser:
    """Parses a course content/assignments listing page (Original Course View)."""

    def parse(
        self,
        html: str,
        course_id: str,
        base_url: str,
        timezone: str,
        now: datetime | None = None,
    ) -> list[Assignment]:
        now = now or datetime.now(ZoneInfo("UTC"))
        soup = BeautifulSoup(html, "html.parser")
        candidates = first_matching(soup, ASSIGNMENT_ITEM_SELECTORS)
        items = [item for item in candidates if not _is_menu_item(item)]

        if candidates and not items:
            logger.info(
                "OriginalCourseParser: every matched item was the course's left-nav menu "
                "(paletteItem:*), not real content — this page is the course menu, not an "
                "assignment listing. See parsers/DOM_NOTES.md for the real content area."
            )
        elif not items:
            logger.warning("OriginalCourseParser: no assignment items matched any known selector")

        assignments: list[Assignment] = []
        for item in items:
            parsed = self._parse_item(item, course_id, base_url, timezone, now)
            if parsed is not None:
                assignments.append(parsed)
        return assignments

    def _parse_item(
        self,
        item: Tag,
        course_id: str,
        base_url: str,
        timezone: str,
        now: datetime,
    ) -> Assignment | None:
        link = item.find("a", href=True)
        if not link:
            logger.warning("Skipping assignment item with no link: %r", attr_str(item, "id"))
            return None
        assert isinstance(link, Tag)

        title = link.get_text(strip=True) or attr_str(link, "aria-label")
        if not title:
            logger.warning("Skipping assignment item with no extractable title")
            return None

        href = attr_str(link, "href")
        if not href:
            logger.warning("Skipping assignment item %r with an empty href", title)
            return None
        url = absolute_url(base_url, href) or href
        item_text = item.get_text(separator=" ", strip=True)

        due_date, due_date_raw, due_date_status = parse_due_date(item_text, timezone)
        points, points_status = parse_points(item_text)
        attachments = extract_attachments(item, base_url)
        external_links = extract_external_links(item, base_url, url)
        rubric_ref = "rubric" if RUBRIC_PATTERN.search(item_text) else None

        blackboard_id = attr_str(item, "id") or course_id_from_href(href)
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

        return Assignment(
            id=assignment_id,
            course_id=course_id,
            kind=classify_kind(title),
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
            fingerprint=resolve_identity(course_id, title, None, None, due_date_raw, points)[0],
            source="playwright",
        )
