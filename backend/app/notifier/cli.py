"""Notifier CLI: one-shot check for new/changed assignments, pushed to
Telegram.

    python -m app.notifier run-once

Meant to be invoked periodically by launchd (see docs/launchd/), not run
as a long-lived loop itself — each invocation is independent and stateless
beyond the shared snapshot cache, so a crashed or killed run just gets
retried on the next scheduled tick instead of needing its own supervision.
"""
from __future__ import annotations

import logging
import sys

import click

from app.blackboard.config import load_settings
from app.blackboard.exceptions import BlackboardError
from app.blackboard.factory import get_provider
from app.blackboard.snapshot_store import SnapshotStore
from app.notifier.diff import classify
from app.notifier.messages import format_event
from app.telegram.client import TelegramError, send_message
from app.telegram.config import load_telegram_settings

logger = logging.getLogger(__name__)

# Effectively "no window" — the notifier needs every assignment (regardless
# of due date) to diff against the cache, not just what's due soon.
ALL_DAYS_WINDOW = 3650


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@click.group()
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
def cli(verbose: bool) -> None:
    """Student Academic Assistant — Blackboard-to-Telegram notifier (Phase 3)."""
    _configure_logging(verbose)


@cli.command(name="run-once")
def run_once() -> None:
    """Check Blackboard once, push a Telegram message for anything new or
    changed, then exit. Safe to run repeatedly (e.g. every 30 min via
    launchd) — it only ever notifies once per new item or due-date change,
    using the same on-disk snapshot cache the `blackboard` CLI already
    maintains.
    """
    settings = load_settings()
    telegram_settings = load_telegram_settings()
    provider = get_provider(settings)
    store = SnapshotStore(settings.snapshot_cache_path)
    is_first_run = not settings.snapshot_cache_path.exists()

    try:
        course_map = {c.id: c for c in provider.get_courses()}
        result = provider.get_upcoming_assignments(
            days=ALL_DAYS_WINDOW, include_overdue=True, include_no_due_date=True
        )
    except BlackboardError as exc:
        logger.error("Could not read Blackboard: %s", exc)
        try:
            send_message(
                telegram_settings.bot_token,
                telegram_settings.chat_id,
                "⚠️ No pude revisar Blackboard: "
                f"{exc}\n\nSi tu sesión expiró, corré `python -m app.blackboard login` "
                "para renovarla (necesita que abras el navegador manualmente).",
            )
        except TelegramError as telegram_exc:
            logger.error("Also could not send the failure notification via Telegram: %s", telegram_exc)
        sys.exit(1)

    all_found = list(result.upcoming) + list(result.overdue) + list(result.no_due_date)

    if is_first_run:
        store.save({a.id: a for a in all_found})
        logger.info(
            "First run: saved a baseline of %d assignment(s), no notifications sent. "
            "Future runs will notify about anything new or changed from here on.",
            len(all_found),
        )
        return

    previous = store.load()
    events = classify(previous, all_found)

    for event in events:
        text = format_event(event, course_map)
        try:
            send_message(telegram_settings.bot_token, telegram_settings.chat_id, text)
            logger.info("Notified: %s (%s)", event.assignment.title, event.kind)
        except TelegramError as exc:
            logger.error("Could not send Telegram notification for %r: %s", event.assignment.title, exc)

    updated = dict(previous)
    updated.update({a.id: a for a in all_found})
    store.save(updated)


if __name__ == "__main__":
    cli()
