"""CourseListParser — parses the Blackboard course list ("My Courses" on
Original Experience, `/ultra/course` on Ultra Experience) into Course DTOs.

Phase 2.1 finding (real UDEM Blackboard): the institution's *base
navigation* being Ultra Experience does NOT mean every course uses Ultra
Course View — UDEM's course cards were reported to show a "Course view"
field that reads "Original Course View" per course. So this parser reads
course_view per card instead of assuming it from the page URL, and the
rest of the system (parsers/dispatch.py) picks OriginalCourseParser vs
UltraCourseParser based on that per-course value, never on the
institution's experience as a whole.

Phase 2.1 update — CONFIRMED against real UDEM markup (shared by the user
from DevTools, redacted of personal data): course cards are
`<article data-course-id="..." class="element-card course-element-card
...">` containing `a.course-title` (the course link, with an
`h4.js-course-title-element` for the name and a `.course-type` span next
to it — believed to be the Course view indicator, exact text not yet
confirmed) and a `[class*="course_username"]` span for the instructor.
Those are now the PRIMARY selectors; the earlier data-testid/ARIA guesses
stay as fallbacks for institutions/skins that don't match this structure.
See parsers/DOM_NOTES.md for exactly what's confirmed vs still assumed.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.blackboard.dto import Course, CourseView
from app.blackboard.parsers.common import absolute_url, attr_str, course_id_from_href, first_matching

logger = logging.getLogger("blackboard.parsers.course_list")

# Candidate containers for one course "card"/list entry. Tried in order.
CARD_SELECTORS = [
    "article[data-course-id]",  # confirmed real UDEM markup (Phase 2.1)
    "article.course-element-card",
    '[data-testid*="course-list-item" i]',
    '[data-testid*="course-card" i]',
    '[role="article"]',
    '[role="listitem"]',
]

# Candidate selectors for the primary link to a course, tried within a card
# first; falls back to scanning the whole page for these if no card
# container matched at all (e.g. Original Experience's flatter markup).
COURSE_LINK_SELECTORS = [
    "a.course-title[href]",  # confirmed real UDEM markup (Phase 2.1)
    'a[href*="/ultra/courses/"]',  # generic Ultra Experience pattern
    'a[href*="course_id="]',  # generic Original Experience pattern
]

# Where the course name text lives, inside the course-title link.
COURSE_TITLE_TEXT_SELECTORS = [
    "h4.js-course-title-element",  # confirmed real UDEM markup (Phase 2.1)
]

# Believed (not yet confirmed) to hold the Original/Ultra Course View
# label. Checked first; _course_view_from_text() falls back to scanning
# the whole card's text if this doesn't contain a recognizable value.
COURSE_TYPE_SELECTORS = [
    ".course-title .course-type",  # confirmed present in real UDEM markup; exact text TBD
    ".course-type",
]

# Confirmed real UDEM markup (Phase 2.1): a span whose class starts with
# "course_username" (with an opaque per-user suffix, hence the wildcard).
INSTRUCTOR_SELECTORS = [
    '[class*="course_username"]',
]

INSTRUCTOR_LABEL_PATTERN = re.compile(r"instructor", re.IGNORECASE)


def _course_view_from_text(text: str) -> CourseView:
    """Never guesses: only returns ORIGINAL/ULTRA when the literal label
    Blackboard displays is found; UNKNOWN otherwise (Step 3 requirement).
    """
    lowered = text.lower()
    if "original course view" in lowered:
        return CourseView.ORIGINAL
    if "ultra course view" in lowered:
        return CourseView.ULTRA
    return CourseView.UNKNOWN


def _extract_labeled_value(lines: list[str], label_pattern: re.Pattern[str]) -> str | None:
    """Handles two layouts seen across Blackboard skins: "Label: value" on
    one line, or "Label" and "value" as separate stacked lines/elements
    (common when a React component renders a label and its value as
    sibling nodes). Returns None rather than guessing when neither matches.
    """
    for i, line in enumerate(lines):
        if not label_pattern.search(line):
            continue
        remainder = label_pattern.sub("", line, count=1).strip(" :–-")
        if remainder:
            return remainder
        if i + 1 < len(lines):
            return lines[i + 1]
    return None


class CourseListParser:
    """Parses a course-list page into normalized Course DTOs."""

    def parse(self, html: str, base_url: str) -> list[Course]:
        soup = BeautifulSoup(html, "html.parser")
        cards = first_matching(soup, CARD_SELECTORS)

        if cards:
            courses = [c for card in cards if (c := self._parse_card(card, base_url)) is not None]
        else:
            # No card container matched — fall back to scanning for course
            # links directly (this is the path Original Experience's
            # simpler "My Courses" module list takes).
            logger.info("No course card containers matched; falling back to direct link scan")
            courses = [
                c
                for link in first_matching(soup, COURSE_LINK_SELECTORS)
                if (c := self._parse_bare_link(link, base_url)) is not None
            ]

        if not courses:
            logger.warning("CourseListParser: no courses found with any known selector strategy")

        seen_ids: set[str] = set()
        deduped: list[Course] = []
        for course in courses:
            if course.id in seen_ids:
                continue
            seen_ids.add(course.id)
            deduped.append(course)
        return deduped

    def _parse_card(self, card: Tag, base_url: str) -> Course | None:
        link = first_matching_within(card, COURSE_LINK_SELECTORS)
        if link is None:
            return None

        href = attr_str(link, "href")
        if not href:
            return None
        absolute = absolute_url(base_url, href)

        # Prefer Blackboard's own data-course-id attribute (confirmed real
        # UDEM markup) — it's the actual identifier Blackboard puts on the
        # card itself, more reliable than parsing one out of a URL.
        course_id = attr_str(card, "data-course-id") or course_id_from_href(href) or absolute
        if not course_id:
            return None

        name = self._extract_name(link) or attr_str(link, "aria-label") or course_id
        card_lines = [line for line in card.get_text(separator="\n", strip=True).split("\n") if line]
        card_text = " ".join(card_lines)

        return Course(
            id=course_id,
            name=name,
            url=absolute or href,
            term=None,  # not reliably present on every skin; left unset rather than guessed
            course_view=self._detect_course_view(card, card_text),
            instructor=self._extract_instructor(card, card_lines),
            source="playwright",
        )

    def _extract_name(self, link: Tag) -> str | None:
        for selector in COURSE_TITLE_TEXT_SELECTORS:
            title_el = link.select_one(selector)
            if title_el is not None:
                text = title_el.get_text(strip=True)
                if text:
                    return text
        return link.get_text(strip=True) or None

    def _detect_course_view(self, card: Tag, card_text: str) -> CourseView:
        for selector in COURSE_TYPE_SELECTORS:
            el = card.select_one(selector)
            if el is not None:
                detected = _course_view_from_text(el.get_text(strip=True))
                if detected != CourseView.UNKNOWN:
                    return detected
        # Fallback: the label might render somewhere other than .course-type
        # (e.g. behind the "more info" toggle, or a different element than
        # believed) — scan the whole card's visible text as a last resort
        # before giving up and reporting UNKNOWN.
        return _course_view_from_text(card_text)

    def _extract_instructor(self, card: Tag, card_lines: list[str]) -> str | None:
        for selector in INSTRUCTOR_SELECTORS:
            el = card.select_one(selector)
            if el is not None:
                text = el.get_text(strip=True)
                if text:
                    return text
        return _extract_labeled_value(card_lines, INSTRUCTOR_LABEL_PATTERN)

    def _parse_bare_link(self, link: Tag, base_url: str) -> Course | None:
        href = attr_str(link, "href")
        if not href:
            return None
        absolute = absolute_url(base_url, href)
        course_id = course_id_from_href(href) or absolute
        if not course_id:
            return None
        name = link.get_text(strip=True) or attr_str(link, "aria-label") or course_id
        return Course(
            id=course_id,
            name=name,
            url=absolute or href,
            term=None,
            course_view=CourseView.UNKNOWN,  # no card context to read a "Course view" label from
            instructor=None,
            source="playwright",
        )


def first_matching_within(container: Tag, selectors: list[str]) -> Tag | None:
    for selector in selectors:
        found = container.select_one(selector)
        if found is not None:
            return found
    return None
