"""Long-polling Telegram bot: routes /tareas, /proxima, /resumen, /start,
and free-form chat.

Only ever acts on TELEGRAM_CHAT_ID (see telegram/config.py) — any other
chat is ignored, so a leaked bot token can't be used to query someone
else's Blackboard data through this bot.

    python -m app.telegram_bot run

Runs until interrupted or killed; meant to be supervised by launchd (see
docs/launchd/) so it restarts automatically if it crashes.
"""
from __future__ import annotations

import logging
import time

import click

from app.blackboard.config import load_settings
from app.blackboard.dto import Assignment, Course
from app.blackboard.exceptions import BlackboardError
from app.blackboard.factory import get_provider
from app.blackboard.provider import BlackboardProvider
from app.telegram.client import TelegramError, get_updates, send_message
from app.telegram.config import TelegramSettings, load_telegram_settings
from app.telegram_bot import commands
from app.telegram_bot.chat import handle_chat
from app.telegram_bot.claude_client import ClaudeClient
from app.telegram_bot.context_store import ContextStore

logger = logging.getLogger(__name__)

UPCOMING_WINDOW_DAYS = 7
POLL_RETRY_DELAY_SECONDS = 5

START_MESSAGE = (
    "Hola! Soy tu asistente de tareas de Blackboard.\n\n"
    "/tareas — ver tus tareas próximas y vencidas\n"
    "/proxima — la más urgente\n"
    "/resumen <número> — detalle de una tarea de la última lista de /tareas\n\n"
    "Una vez que elijas una tarea con /resumen también podés escribirme en lenguaje natural "
    "sobre ella."
)


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _command_token(text: str) -> str:
    """'/tareas@my_bot algo' -> '/tareas' (Telegram appends the bot's own
    username to commands in group chats; harmless to strip in private chats
    too)."""
    first_word = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    return first_word.split("@")[0]


def route_message(
    text: str,
    provider: BlackboardProvider,
    store: ContextStore,
    claude_client: ClaudeClient,
) -> str:
    """Pure routing: given a message and already-constructed dependencies,
    fetches Blackboard data exactly once and returns the reply text. Split
    out from the Telegram plumbing so it's directly unit-testable."""
    try:
        course_map: dict[str, Course] = {c.id: c for c in provider.get_courses()}
        result = provider.get_upcoming_assignments(
            days=UPCOMING_WINDOW_DAYS, include_overdue=True, include_no_due_date=True
        )
    except BlackboardError as exc:
        return f"⚠️ No pude leer Blackboard: {exc}"

    all_assignments: dict[str, Assignment] = {
        a.id: a for a in list(result.upcoming) + list(result.overdue) + list(result.no_due_date)
    }

    token = _command_token(text)
    if token == "/tareas":
        return commands.handle_tareas(
            list(result.upcoming), list(result.overdue), len(result.no_due_date), course_map, store
        )
    if token == "/proxima":
        return commands.handle_proxima(list(result.upcoming), list(result.overdue), course_map)
    if token == "/resumen":
        arg = text.strip()[len(token) :].strip()
        return commands.handle_resumen(arg, all_assignments, course_map, store)
    if token == "/start":
        return START_MESSAGE

    return handle_chat(text, all_assignments, course_map, store, claude_client)


def handle_update(
    update: dict,
    provider: BlackboardProvider,
    store: ContextStore,
    claude_client: ClaudeClient,
    telegram_settings: TelegramSettings,
) -> None:
    message = update.get("message")
    if not message:
        return
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "")
    if not text:
        return

    if chat_id != telegram_settings.chat_id:
        logger.warning("Ignoring message from unauthorized chat_id=%s", chat_id)
        return

    reply = route_message(text, provider, store, claude_client)

    try:
        send_message(telegram_settings.bot_token, chat_id, reply)
    except TelegramError as exc:
        logger.error("Could not send reply to chat_id=%s: %s", chat_id, exc)


def poll_once(
    provider: BlackboardProvider,
    store: ContextStore,
    claude_client: ClaudeClient,
    telegram_settings: TelegramSettings,
    offset: int | None,
) -> int | None:
    """Fetches and processes at most one batch of updates. Returns the next
    offset to use (unchanged if nothing new came in or Telegram couldn't be
    reached)."""
    try:
        updates = get_updates(telegram_settings.bot_token, offset=offset)
    except TelegramError as exc:
        logger.error("Could not poll Telegram: %s", exc)
        return offset

    for update in updates:
        offset = update["update_id"] + 1
        store.set_offset(offset)
        handle_update(update, provider, store, claude_client, telegram_settings)

    return offset


@click.group()
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
def cli(verbose: bool) -> None:
    """Student Academic Assistant — Telegram bot (Phase 3)."""
    _configure_logging(verbose)


@cli.command()
def run() -> None:
    """Long-poll Telegram for messages and respond, forever."""
    settings = load_settings()
    telegram_settings = load_telegram_settings()
    provider = get_provider(settings)
    store = ContextStore(settings.state_dir / "telegram_bot_context.sqlite3")
    claude_client = ClaudeClient()

    offset = store.get_offset()
    logger.info("Bot started, listening for messages from chat_id=%s", telegram_settings.chat_id)

    while True:
        new_offset = poll_once(provider, store, claude_client, telegram_settings, offset)
        if new_offset == offset:
            # getUpdates errored or returned nothing new — avoid busy-looping.
            time.sleep(POLL_RETRY_DELAY_SECONDS)
        offset = new_offset


if __name__ == "__main__":
    cli()
