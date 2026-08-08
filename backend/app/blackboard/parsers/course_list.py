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

HONESTY NOTE: this was written from a text description of the UDEM course
cards (fields: Course ID, Course name, Course view, Instructor, Open, More
info), not from captured real HTML — no real DOM sample was available.
The card/container selectors below are best-effort candidates for a
React-rendered Ultra page (data-testid / ARIA patterns are typical there);
the label-based field extraction (course_view, instructor) is a closer bet
because it's driven by literal label text the user described on-screen,
which tends to survive UI/selector changes better than CSS classes. Both
still need verification against real HTML — see backend/README.md.
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
    '[data-testid*="course-list-item" i]',
    '[data-testid*="course-card" i]',
    '[role="article"]',
    '[role="listitem"]',
]

# Candidate selectors for the primary link to a course, tried within a card
# first; falls back to scanning the whole page for these if no card
# container matched at all (e.g. Original Experience's flatter markup).
COURSE_LINK_SELECTORS = [
    'a[href*="/ultra/courses/"]',   # Ultra Experience course list entries
    'a[href*="course_id="]',        # Original Experience "My Courses" module
]

INSTRUCTOR_LABEL_PATTERN = re.compile(r"instructor", re.IGNORECASE)


def _detect_course_view(card_text: str) -> CourseView:
    """Never guesses: only returns ORIGINAL/ULTRA when the literal label
    Blackboard displays is found; UNKNOWN otherwise (Step 3 requirement).
    """
    lowered = card_text.lower()
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
        course_id = course_id_from_href(href) or absolute
        if not course_id:
            return None

        name = link.get_text(strip=True) or attr_str(link, "aria-label") or course_id
        card_lines = [line for line in card.get_text(separator="\n", strip=True).split("\n") if line]
        card_text = " ".join(card_lines)

        return Course(
            id=course_id,
            name=name,
            url=absolute or href,
            term=None,  # not reliably present on every skin; left unset rather than guessed
            course_view=_detect_course_view(card_text),
            instructor=_extract_labeled_value(card_lines, INSTRUCTOR_LABEL_PATTERN),
            source="playwright",
        )

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
