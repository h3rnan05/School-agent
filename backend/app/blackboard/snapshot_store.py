"""Local, file-based cache of the last-seen assignments.

Phase 2 deliberately does not connect to PostgreSQL yet (see
ARCHITECTURE.md section 18 / Phase 2 scope). To still demonstrate change
detection (section 9) across separate CLI runs, the last snapshot of each
assignment is cached as JSON under the local state directory (gitignored,
never committed). This file is not sensitive (it holds the same assignment
data Blackboard already shows the user) but still lives outside the repo
to keep the module's on-disk footprint in one place.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.blackboard.dto import (
    Assignment,
    AssignmentKind,
    AssignmentTimingStatus,
    AttachmentRef,
    DueDateStatus,
    FieldStatus,
)


def _assignment_to_dict(assignment: Assignment) -> dict:
    data = asdict(assignment)
    data["due_date"] = assignment.due_date.isoformat() if assignment.due_date else None
    return data


def _assignment_from_dict(data: dict) -> Assignment:
    payload = dict(data)
    payload["kind"] = AssignmentKind(payload["kind"])
    payload["due_date_status"] = DueDateStatus(payload["due_date_status"])
    payload["points_status"] = FieldStatus(payload["points_status"])
    payload["timing_status"] = AssignmentTimingStatus(payload["timing_status"])
    payload["due_date"] = datetime.fromisoformat(payload["due_date"]) if payload["due_date"] else None
    payload["attachments"] = tuple(AttachmentRef(**a) for a in payload["attachments"])
    payload["external_links"] = tuple(payload["external_links"])
    return Assignment(**payload)


class SnapshotStore:
    """Keyed by assignment id. Last write wins per id."""

    def __init__(self, path: Path):
        self._path = path

    def load(self) -> dict[str, Assignment]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return {aid: _assignment_from_dict(data) for aid, data in raw.items()}

    def save(self, assignments: dict[str, Assignment]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serialized = {aid: _assignment_to_dict(a) for aid, a in assignments.items()}
        self._path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
