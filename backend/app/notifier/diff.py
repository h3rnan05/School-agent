"""Classifies what changed since the last check, for notification purposes.

Reuses blackboard/changes.py's field-level diff (the same one the CLI's
`upcoming`/`assignments` commands already print as `[CHANGED]` lines)
rather than reinventing comparison logic. The one thing this module adds
on top is treating "not in the previous snapshot at all" as a real event
(NEW) — changes.py's diff_assignments only compares two snapshots of the
*same* assignment, so it has nothing to say about brand-new ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.blackboard.changes import diff_assignments
from app.blackboard.dto import Assignment

NotifierEventKind = Literal["NEW", "DUE_DATE_CHANGED"]


@dataclass(frozen=True)
class NotifierEvent:
    kind: NotifierEventKind
    assignment: Assignment
    old_due_date: datetime | None = None


def classify(previous: dict[str, Assignment], found: list[Assignment]) -> list[NotifierEvent]:
    """`previous == {}` is NOT treated specially here — on a genuinely empty
    cache this would flag every assignment as NEW. The guard against that
    (so a fresh install doesn't blast one notification per existing
    assignment) lives in notifier/cli.py's first-run bootstrap check, one
    layer up, where it belongs (that's a "don't spam on first run" policy
    decision, not a diffing concern).
    """
    events: list[NotifierEvent] = []
    for assignment in found:
        old = previous.get(assignment.id)
        if old is None:
            events.append(NotifierEvent(kind="NEW", assignment=assignment))
            continue
        for change in diff_assignments(old, assignment):
            if change.field != "due_date":
                continue
            old_value = change.old_value
            if isinstance(old_value, datetime) or old_value is None:
                events.append(
                    NotifierEvent(kind="DUE_DATE_CHANGED", assignment=assignment, old_due_date=old_value)
                )
    return events
