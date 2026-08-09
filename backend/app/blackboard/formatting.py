"""Human-readable formatting for Assignment fields.

Shared by cli.py and the notifier/telegram_bot modules so the timezone
conversion logic (the actual tricky part) lives in exactly one place —
see the docstring on format_due_date_parts for why this matters.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from app.blackboard.dto import Assignment


def format_due_date_parts(assignment: Assignment) -> tuple[str, str]:
    """Returns (date, time) as separate display strings, in the assignment's
    OWN timezone (the one it was interpreted with), not UTC. due_date is
    stored internally as UTC for consistent comparisons (bucketing, change
    detection), but showing UTC to a human would silently shift the
    wall-clock time Blackboard actually displayed — exactly the "silent
    conversion" Phase 2.1 said not to do.
    """
    if assignment.due_date is not None:
        try:
            local = assignment.due_date.astimezone(ZoneInfo(assignment.timezone))
        except Exception:  # noqa: BLE001 - unknown/invalid tz name, fall back to UTC rather than crash
            local = assignment.due_date
        return (local.strftime("%B %d, %Y"), local.strftime("%I:%M %p"))
    if assignment.due_date_status.value == "UNPARSEABLE":
        return ("DATA_UNAVAILABLE", "DATA_UNAVAILABLE")
    return ("(no due date)", "-")


def format_points(assignment: Assignment) -> str:
    if assignment.points is not None:
        return f"{assignment.points:g} points"
    if assignment.points_status.value == "DATA_UNAVAILABLE":
        return "DATA_UNAVAILABLE"
    return "(not specified)"
