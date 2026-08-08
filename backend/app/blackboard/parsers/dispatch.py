"""AssignmentParser — picks the right course-view-specific parser for a
given course, so callers (PlaywrightBlackboardProvider) never have to know
about OriginalCourseParser/UltraCourseParser directly.

Routing is by `course.course_view`, which is read per-course from the
course list page (see course_list.py) — never assumed from the
institution's overall Blackboard Experience. This is the direct fix for
the Phase 2.1 finding that an Ultra Experience institution (UDEM) can
still have Original Course View courses.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.blackboard.dto import Assignment, Course, CourseView
from app.blackboard.parsers.original_course import OriginalCourseParser
from app.blackboard.parsers.ultra_course import UltraCourseParser

logger = logging.getLogger("blackboard.parsers.dispatch")


class AssignmentParser:
    def __init__(self) -> None:
        self._original = OriginalCourseParser()
        self._ultra = UltraCourseParser()

    def parse(
        self,
        html: str,
        course: Course,
        base_url: str,
        timezone: str,
        now: datetime | None = None,
    ) -> list[Assignment]:
        if course.course_view == CourseView.ULTRA:
            return self._ultra.parse(html, course.id, base_url, timezone, now)

        if course.course_view == CourseView.ORIGINAL:
            return self._original.parse(html, course.id, base_url, timezone, now)

        # UNKNOWN: we don't guess *data* (due dates, points, etc. are never
        # invented), but for *routing* we still make one disclosed,
        # low-risk attempt — Original Course View's parser is read-only and
        # simply returns [] with its own warning if nothing matches, so
        # trying it is not the same as guessing a due date. Ultra's parser
        # is an unimplemented stub either way (see ultra_course.py), so
        # skipping straight to "unsupported" here would be strictly worse.
        logger.warning(
            "Course %r has course_view=UNKNOWN; attempting OriginalCourseParser as a "
            "disclosed best-effort fallback (see parsers/dispatch.py docstring). If this "
            "course is actually Ultra Course View, expect an empty result.",
            course.id,
        )
        return self._original.parse(html, course.id, base_url, timezone, now)
