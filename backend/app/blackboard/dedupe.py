"""Stable identity for assignments, so re-scraping never creates duplicates.

Priority, as specified in ARCHITECTURE.md / Phase 2 scope:

1. Blackboard's own assignment id (parsed from the DOM/URL) — most stable.
2. The assignment's Blackboard URL — stable enough in practice, changes
   only if the assignment is recreated.
3. A content fingerprint (course + title + due date + points) — last
   resort, used only when Blackboard gives us neither of the above.

The fingerprint is intentionally NOT the primary key: two genuinely
different assignments could collide if titles and dates coincided, and a
legitimate title/date edit would look like a new assignment. It exists so
we still deduplicate something instead of creating unlimited duplicates
when Blackboard's markup doesn't expose a stable id or URL.
"""
from __future__ import annotations

import hashlib
from enum import Enum


class IdentitySource(str, Enum):
    BLACKBOARD_ID = "BLACKBOARD_ID"
    URL = "URL"
    FINGERPRINT = "FINGERPRINT"


def compute_fingerprint(
    course_id: str,
    title: str,
    due_date_raw: str | None,
    points: float | None,
) -> str:
    normalized = "|".join(
        [
            course_id.strip().lower(),
            " ".join(title.strip().lower().split()),
            (due_date_raw or "").strip().lower(),
            "" if points is None else f"{points:g}",
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def resolve_identity(
    course_id: str,
    title: str,
    blackboard_id: str | None,
    url: str | None,
    due_date_raw: str | None,
    points: float | None,
) -> tuple[str, IdentitySource]:
    if blackboard_id:
        return blackboard_id, IdentitySource.BLACKBOARD_ID
    if url:
        return url, IdentitySource.URL
    return (
        compute_fingerprint(course_id, title, due_date_raw, points),
        IdentitySource.FINGERPRINT,
    )
