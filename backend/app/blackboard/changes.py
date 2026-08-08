"""Change detection between two snapshots of the same assignment.

This mirrors the AssignmentChangeLog table from ARCHITECTURE.md section 5,
but Phase 2 has no database yet (see scope note in cli.py), so it operates
on two in-memory Assignment objects and returns plain records. Wiring this
into AssignmentChangeLog rows is a later phase's job.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.blackboard.dto import Assignment

TRACKED_FIELDS = ("title", "description", "due_date", "points", "url")


@dataclass(frozen=True)
class FieldChange:
    assignment_id: str
    field: str
    old_value: object
    new_value: object


def diff_assignments(old: Assignment, new: Assignment) -> list[FieldChange]:
    if old.id != new.id:
        raise ValueError("diff_assignments requires two snapshots of the same assignment id")

    changes: list[FieldChange] = []
    for field_name in TRACKED_FIELDS:
        old_value = getattr(old, field_name)
        new_value = getattr(new, field_name)
        if old_value != new_value:
            changes.append(
                FieldChange(
                    assignment_id=new.id,
                    field=field_name,
                    old_value=old_value,
                    new_value=new_value,
                )
            )
    return changes
