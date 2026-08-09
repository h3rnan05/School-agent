"""Free-form (non-command) chat: resolves which assignment the
conversation is currently "focused" on (set via /resumen), builds a
context string from real Blackboard data only, and asks Claude for a
reply. If nothing is in focus, it says so instead of guessing which
assignment the student means.
"""
from __future__ import annotations

from app.blackboard.dto import Assignment, Course
from app.blackboard.formatting import format_due_date_parts, format_points
from app.telegram_bot.claude_client import ClaudeClient
from app.telegram_bot.context_store import ContextStore

NO_FOCUS_CONTEXT = (
    "No hay ninguna tarea puntual en foco todavía. Decile al estudiante que use /tareas para ver "
    "la lista y /resumen <número> para elegir una antes de preguntar sobre su contenido."
)


def _assignment_context(assignment: Assignment, course_map: dict[str, Course]) -> str:
    course = course_map.get(assignment.course_id)
    due_date, time_ = format_due_date_parts(assignment)
    due_date_line = due_date if time_ in ("-", "DATA_UNAVAILABLE") else f"{due_date}, {time_}"
    return (
        f"- Tarea: {assignment.title}\n"
        f"  Materia: {course.name if course else assignment.course_id}\n"
        f"  Fecha de entrega: {due_date_line}\n"
        f"  Puntos: {format_points(assignment)}\n"
        f"  Link: {assignment.url}"
    )


def handle_chat(
    user_message: str,
    all_assignments: dict[str, Assignment],
    course_map: dict[str, Course],
    store: ContextStore,
    claude_client: ClaudeClient,
) -> str:
    focus_id = store.get_focus_assignment_id()
    focus = all_assignments.get(focus_id) if focus_id else None

    context = _assignment_context(focus, course_map) if focus is not None else NO_FOCUS_CONTEXT
    return claude_client.reply(context=context, user_message=user_message)
