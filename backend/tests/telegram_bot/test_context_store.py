from __future__ import annotations

from app.telegram_bot.context_store import ContextStore


def test_offset_round_trips(tmp_path):
    store = ContextStore(tmp_path / "bot_state.sqlite3")

    assert store.get_offset() is None

    store.set_offset(42)

    assert store.get_offset() == 42


def test_last_listing_round_trips(tmp_path):
    store = ContextStore(tmp_path / "bot_state.sqlite3")

    assert store.get_last_listing() == []

    store.set_last_listing(["_a1", "_a2", "_a3"])

    assert store.get_last_listing() == ["_a1", "_a2", "_a3"]


def test_focus_assignment_round_trips(tmp_path):
    store = ContextStore(tmp_path / "bot_state.sqlite3")

    assert store.get_focus_assignment_id() is None

    store.set_focus_assignment_id("_a7")

    assert store.get_focus_assignment_id() == "_a7"


def test_state_persists_across_separate_store_instances(tmp_path):
    path = tmp_path / "bot_state.sqlite3"
    ContextStore(path).set_offset(99)

    reopened = ContextStore(path)

    assert reopened.get_offset() == 99


def test_setting_same_key_twice_overwrites_not_duplicates(tmp_path):
    store = ContextStore(tmp_path / "bot_state.sqlite3")

    store.set_offset(1)
    store.set_offset(2)

    assert store.get_offset() == 2
