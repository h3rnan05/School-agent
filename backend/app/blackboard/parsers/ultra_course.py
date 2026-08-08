"""UltraCourseParser — parses assignment/content listings for a course
running Blackboard's Ultra Course View.

NOT YET IMPLEMENTED. No real Ultra Course View course content page was
available to inspect during Phase 2.1 — the UDEM course used for
validation was Original Course View. Rather than guess Ultra's (heavily
React-driven, largely non-semantic) DOM structure with zero evidence, this
returns an empty list and logs a clear warning, so callers can tell "no
assignments found" (data problem) apart from "this course type isn't
supported yet" (capability gap).

To implement this for real: run `blackboard assignments <course_id>`
against an Ultra Course View course, capture the resulting HTML/selectors
(see backend/README.md), and this file is the only thing that needs
filling in — parsers/dispatch.py already routes Ultra-view courses here.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.blackboard.dto import Assignment

logger = logging.getLogger("blackboard.parsers.ultra_course")


class UltraCourseParser:
    """Stub. See module docstring — do not treat an empty result from this
    as "no assignments"; it means Ultra Course View parsing isn't built yet.
    """

    def parse(
        self,
        html: str,
        course_id: str,
        base_url: str,
        timezone: str,
        now: datetime | None = None,
    ) -> list[Assignment]:
        logger.warning(
            "UltraCourseParser.parse() called for course_id=%r: Ultra Course View parsing "
            "is not implemented yet (no real DOM sample was available). Returning no "
            "assignments rather than guessing.",
            course_id,
        )
        return []
