"""Fixed-command handlers for the bot: /tareas, /proxima, /resumen.

Each handler takes data already resolved by bot.py (course_map, the
assignment buckets) rather than reaching into Blackboard itself, so a
single incoming Telegram message only ever triggers one Blackboard read
regardless of which command it is.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.blackboard.dto import Assignment, Course
from app.blackboard.formatting import format_due_date_parts, format_points
from app.telegram_bot.context_store import ContextStore

UPCOMING_WINDOW_DAYS = 7

# Sentinels so min()/max() over a bucket stay type-safe even though
# due_date is Optional — an assignment with no due date should never
# actually appear in the upcoming/overdue buckets, but falling back to
# "least urgent" instead of crashing is the right failure mode if it ever did.
_FAR_FUTURE = datetime.max.replace(tzinfo=timezone.utc)
_FAR_PAST = datetime.min.replace(tzinfo=timezone.utc)


def _due_date_line(assignment: Assignment) -> str:
    due_date, time_ = format_due_date_parts(assignment)
    if time_ in ("-", "DATA_UNAVAILABLE"):
        return due_date
    return f"{due_date}, {time_}"


def _detail_block(assignment: Assignment, course_map: dict[str, Course]) -> str:
    course = course_map.get(assignment.course_id)
    return (
        f"{assignment.title}\n"
        f"Materia: {course.name if course else assignment.course_id}\n"
        f"Fecha de entrega: {_due_date_line(assignment)}\n"
        f"Puntos: {format_points(assignment)}\n"
        f"Link: {assignment.url}"
    )


def handle_tareas(
    upcoming: list[Assignment],
    overdue: list[Assignment],
    no_due_date_count: int,
    course_map: dict[str, Course],
    store: ContextStore,
) -> str:
    numbered = upcoming + overdue
    store.set_last_listing([a.id for a in numbered])

    if not numbered and no_due_date_count == 0:
        return "No encontré ninguna tarea todavía."

    lines: list[str] = []
    if upcoming:
        lines.append(f"📅 Próximas (siguientes {UPCOMING_WINDOW_DAYS} días):")
        for i, a in enumerate(upcoming, start=1):
            course = course_map.get(a.course_id)
            lines.append(f"{i}. {a.title} — {course.name if course else a.course_id} — {_due_date_line(a)}")
    if overdue:
        lines.append("")
        lines.append("🔴 Vencidas:")
        for i, a in enumerate(overdue, start=len(upcoming) + 1):
            course = course_map.get(a.course_id)
            lines.append(f"{i}. {a.title} — {course.name if course else a.course_id} — {_due_date_line(a)}")
    if no_due_date_count:
        lines.append("")
        lines.append(f"ℹ️ Hay {no_due_date_count} tarea(s) más sin fecha de entrega configurada en Blackboard.")
    if numbered:
        lines.append("")
        lines.append("Escribí /resumen <número> para ver el detalle de una.")
    return "\n".join(lines)


def handle_proxima(upcoming: list[Assignment], overdue: list[Assignment], course_map: dict[str, Course]) -> str:
    if upcoming:
        candidate = min(upcoming, key=lambda a: a.due_date or _FAR_FUTURE)
    elif overdue:
        candidate = max(overdue, key=lambda a: a.due_date or _FAR_PAST)
    else:
        return "No tenés ninguna tarea con fecha próxima ni vencida ahora mismo."

    return _detail_block(candidate, course_map)


def handle_resumen(
    arg: str,
    all_assignments: dict[str, Assignment],
    course_map: dict[str, Course],
    store: ContextStore,
) -> str:
    arg = arg.strip()
    if not arg.isdigit():
        return "Usá /resumen <número> — primero corré /tareas para ver la lista numerada."

    index = int(arg)
    listing = store.get_last_listing()
    if index < 1 or index > len(listing):
        return f"No hay una tarea número {index}. Corré /tareas para ver la lista actual."

    assignment = all_assignments.get(listing[index - 1])
    if assignment is None:
        return "Esa tarea ya no está disponible (puede que la lista haya cambiado) — corré /tareas de nuevo."

    store.set_focus_assignment_id(assignment.id)
    return (
        _detail_block(assignment, course_map)
        + "\n\nAhora podés preguntarme algo sobre esta tarea en el chat (no tengo el enunciado "
        "completo todavía, así que si querés ayuda con el contenido pegámelo vos)."
    )
