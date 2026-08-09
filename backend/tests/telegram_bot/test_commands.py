from __future__ import annotations

from datetime import datetime, timezone

from app.telegram_bot.commands import handle_proxima, handle_resumen, handle_tareas
from app.telegram_bot.context_store import ContextStore
from tests.blackboard.factories import make_assignment, make_course


def test_tareas_with_nothing_at_all(tmp_path):
    store = ContextStore(tmp_path / "state.sqlite3")

    text = handle_tareas([], [], 0, {}, store)

    assert "No encontré ninguna tarea" in text
    assert store.get_last_listing() == []


def test_tareas_numbers_upcoming_then_overdue_and_saves_listing(tmp_path):
    store = ContextStore(tmp_path / "state.sqlite3")
    course = make_course(id="_1", name="FINC 301")
    upcoming = [make_assignment(id="_u1", course_id="_1", title="Upcoming task")]
    overdue = [make_assignment(id="_o1", course_id="_1", title="Overdue task")]

    text = handle_tareas(upcoming, overdue, no_due_date_count=3, course_map={"_1": course}, store=store)

    assert "1. Upcoming task" in text
    assert "2. Overdue task" in text
    assert "FINC 301" in text
    assert "Hay 3 tarea(s) más sin fecha" in text
    assert store.get_last_listing() == ["_u1", "_o1"]


def test_proxima_prefers_nearest_upcoming(tmp_path):
    course = make_course(id="_1")
    near = make_assignment(id="_a", course_id="_1", title="Near", due_date=datetime(2026, 8, 10, tzinfo=timezone.utc))
    far = make_assignment(id="_b", course_id="_1", title="Far", due_date=datetime(2026, 9, 10, tzinfo=timezone.utc))

    text = handle_proxima(upcoming=[far, near], overdue=[], course_map={"_1": course})

    assert "Near" in text
    assert "Far" not in text


def test_proxima_falls_back_to_most_recently_overdue(tmp_path):
    course = make_course(id="_1")
    older = make_assignment(id="_a", course_id="_1", title="Older", due_date=datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = make_assignment(id="_b", course_id="_1", title="Newer", due_date=datetime(2026, 6, 1, tzinfo=timezone.utc))

    text = handle_proxima(upcoming=[], overdue=[older, newer], course_map={"_1": course})

    assert "Newer" in text


def test_proxima_with_nothing_at_all():
    text = handle_proxima(upcoming=[], overdue=[], course_map={})

    assert "No tenés ninguna tarea" in text


def test_resumen_resolves_by_number_from_last_listing(tmp_path):
    store = ContextStore(tmp_path / "state.sqlite3")
    store.set_last_listing(["_a1", "_a2"])
    course = make_course(id="_1", name="FINC 301")
    assignment = make_assignment(id="_a2", course_id="_1", title="Second task")

    text = handle_resumen(
        "2", all_assignments={"_a2": assignment}, course_map={"_1": course}, store=store
    )

    assert "Second task" in text
    assert store.get_focus_assignment_id() == "_a2"


def test_resumen_rejects_non_numeric_argument(tmp_path):
    store = ContextStore(tmp_path / "state.sqlite3")

    text = handle_resumen("abc", all_assignments={}, course_map={}, store=store)

    assert "Usá /resumen <número>" in text


def test_resumen_rejects_out_of_range_index(tmp_path):
    store = ContextStore(tmp_path / "state.sqlite3")
    store.set_last_listing(["_a1"])

    text = handle_resumen("5", all_assignments={}, course_map={}, store=store)

    assert "No hay una tarea número 5" in text


def test_resumen_handles_stale_listing_pointing_at_gone_assignment(tmp_path):
    store = ContextStore(tmp_path / "state.sqlite3")
    store.set_last_listing(["_gone"])

    text = handle_resumen("1", all_assignments={}, course_map={}, store=store)

    assert "ya no está disponible" in text
