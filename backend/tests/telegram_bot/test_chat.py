from __future__ import annotations

from app.telegram_bot.chat import NO_FOCUS_CONTEXT, handle_chat
from app.telegram_bot.context_store import ContextStore
from tests.blackboard.factories import make_assignment, make_course


class _FakeClaudeClient:
    def __init__(self, reply_text: str = "respuesta"):
        self._reply_text = reply_text
        self.calls: list[dict] = []

    def reply(self, context: str, user_message: str) -> str:
        self.calls.append({"context": context, "user_message": user_message})
        return self._reply_text


def test_chat_with_no_focus_tells_claude_there_is_none(tmp_path):
    store = ContextStore(tmp_path / "state.sqlite3")
    claude = _FakeClaudeClient()

    handle_chat("hola", all_assignments={}, course_map={}, store=store, claude_client=claude)

    assert claude.calls[0]["context"] == NO_FOCUS_CONTEXT
    assert claude.calls[0]["user_message"] == "hola"


def test_chat_with_focus_includes_real_assignment_data(tmp_path):
    store = ContextStore(tmp_path / "state.sqlite3")
    store.set_focus_assignment_id("_a1")
    course = make_course(id="_1", name="FINC 301")
    assignment = make_assignment(id="_a1", course_id="_1", title="Actividad 2")
    claude = _FakeClaudeClient()

    handle_chat(
        "que pide?",
        all_assignments={"_a1": assignment},
        course_map={"_1": course},
        store=store,
        claude_client=claude,
    )

    context = claude.calls[0]["context"]
    assert "Actividad 2" in context
    assert "FINC 301" in context


def test_chat_returns_claude_clients_reply(tmp_path):
    store = ContextStore(tmp_path / "state.sqlite3")
    claude = _FakeClaudeClient(reply_text="acá está tu respuesta")

    result = handle_chat("hola", all_assignments={}, course_map={}, store=store, claude_client=claude)

    assert result == "acá está tu respuesta"


def test_chat_focus_pointing_at_missing_assignment_falls_back_to_no_focus(tmp_path):
    store = ContextStore(tmp_path / "state.sqlite3")
    store.set_focus_assignment_id("_gone")
    claude = _FakeClaudeClient()

    handle_chat("hola", all_assignments={}, course_map={}, store=store, claude_client=claude)

    assert claude.calls[0]["context"] == NO_FOCUS_CONTEXT
