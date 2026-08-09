"""Builds the Telegram message text for a NotifierEvent.

Written in Spanish, unlike the CLI (English, generic dev tooling meant to
be shareable across institutions) — this is a personal notification
channel for one user.
"""
from __future__ import annotations

from app.blackboard.dto import Course
from app.blackboard.formatting import format_due_date_parts, format_points
from app.notifier.diff import NotifierEvent


def _due_date_display(due_date: str, time_: str) -> str:
    if time_ in ("-", "DATA_UNAVAILABLE"):
        return due_date
    return f"{due_date}, {time_}"


def format_event(event: NotifierEvent, course_map: dict[str, Course]) -> str:
    assignment = event.assignment
    course = course_map.get(assignment.course_id)
    course_name = course.name if course else assignment.course_id
    due_date, time_ = format_due_date_parts(assignment)

    if event.kind == "NEW":
        return (
            "📌 Tarea nueva detectada\n\n"
            f"Materia: {course_name}\n"
            f"Tarea: {assignment.title}\n"
            f"Fecha de entrega: {_due_date_display(due_date, time_)}\n"
            f"Puntos: {format_points(assignment)}\n"
            f"Link: {assignment.url}"
        )

    old = event.old_due_date.isoformat() if event.old_due_date else "(sin fecha)"
    return (
        "⚠️ Cambió la fecha de entrega\n\n"
        f"Materia: {course_name}\n"
        f"Tarea: {assignment.title}\n"
        f"Antes: {old}\n"
        f"Ahora: {_due_date_display(due_date, time_)}\n"
        f"Link: {assignment.url}"
    )
