"""Normalized data objects produced by the Blackboard module.

These are plain dataclasses, independent of Playwright and independent of
any database model. The rest of the system (future ingestion/DB layer)
only ever sees these, never raw HTML or Playwright objects.

Missing data is never invented. Two distinct "we don't know" states exist:

- ``None`` / ``FieldStatus.NOT_PRESENT``: the field genuinely doesn't apply
  (e.g. an assignment with no due date, no points).
- ``FieldStatus.DATA_UNAVAILABLE``: the field should exist but the parser
  could not extract it (e.g. Blackboard changed its markup). This is a
  signal to fix the parser, not a value to guess at.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal

ProviderSource = Literal["playwright", "official"]


class FieldStatus(str, Enum):
    OK = "OK"
    NOT_PRESENT = "NOT_PRESENT"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class DueDateStatus(str, Enum):
    OK = "OK"
    NO_DUE_DATE = "NO_DUE_DATE"
    UNPARSEABLE = "UNPARSEABLE"


class AssignmentTimingStatus(str, Enum):
    """Where an assignment sits relative to "now", computed at read time.

    This is deliberately NOT the same enum as the lifecycle AssignmentStatus
    from ARCHITECTURE.md (DISCOVERED/PLANNED/.../SUBMITTED) — that one lives
    in the future DB layer and is never touched by this module. This one is
    purely "how urgent does this look right now".
    """

    UPCOMING = "UPCOMING"
    DUE_TODAY = "DUE_TODAY"
    OVERDUE = "OVERDUE"
    NO_DUE_DATE = "NO_DUE_DATE"
    UNKNOWN = "UNKNOWN"


class AssignmentKind(str, Enum):
    ASSIGNMENT = "assignment"
    QUIZ = "quiz"
    PROJECT = "project"
    DISCUSSION = "discussion"
    ANNOUNCEMENT = "announcement"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Course:
    id: str
    name: str
    url: str
    term: str | None
    source: ProviderSource


@dataclass(frozen=True)
class AttachmentRef:
    """Reference only — no content is downloaded in this phase."""

    filename: str | None
    url: str | None
    file_type: str | None


@dataclass(frozen=True)
class Assignment:
    id: str
    course_id: str
    kind: AssignmentKind
    title: str
    description: str | None
    instructions: str | None

    due_date: datetime | None  # timezone-aware, normalized to UTC
    due_date_raw: str | None  # original text as found on the page, for debugging
    due_date_status: DueDateStatus
    timezone: str  # IANA timezone used to interpret due_date_raw

    points: float | None
    points_status: FieldStatus

    url: str
    timing_status: AssignmentTimingStatus

    rubric_ref: str | None  # reference only (e.g. a label/url), not the full rubric
    attachments: tuple[AttachmentRef, ...] = field(default_factory=tuple)
    external_links: tuple[str, ...] = field(default_factory=tuple)

    fingerprint: str = ""  # fallback identity, see dedupe.py
    source: ProviderSource = "playwright"


@dataclass(frozen=True)
class UpcomingAssignments:
    """Result of get_upcoming_assignments — buckets are never merged silently."""

    upcoming: tuple[Assignment, ...]
    overdue: tuple[Assignment, ...] = field(default_factory=tuple)
    no_due_date: tuple[Assignment, ...] = field(default_factory=tuple)
