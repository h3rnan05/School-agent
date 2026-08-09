"""Thin wrapper around the Anthropic SDK for the bot's free-form chat.

Only the fields blackboard/dto.py actually populates today (title, course,
due date, points, kind, url) are ever given to the model as context —
never description/instructions, which the parser currently leaves unset
(see parsers/original_course.py: "left unset in list view; a detail-page
fetch is a later phase's job"). The system prompt says so explicitly so
Claude doesn't hallucinate assignment content it was never given.
"""
from __future__ import annotations

import os

import anthropic

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "Sos un asistente que ayuda a un estudiante universitario a organizarse con sus tareas de "
    "Blackboard. Respondés en español, de forma breve y directa (esto es un chat de Telegram, no "
    "un ensayo).\n\n"
    "IMPORTANTE: solo tenés el título, materia, fecha de entrega, puntos y link de cada tarea — "
    "NO tenés el enunciado ni las instrucciones completas (todavía no se extraen de Blackboard). "
    "Si el estudiante pregunta qué pide la tarea o pide ayuda con el contenido, decile claramente "
    "que no tenés el enunciado y sugerile que te lo pegue él mismo si quiere ayuda con eso, en vez "
    "de inventar de qué se trata.\n\n"
    "Nunca digas que vas a entregar, subir o completar algo en Blackboard por él — no podés hacer "
    "eso, solo podés leer datos y conversar."
)


class ClaudeClient:
    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ):
        self._client = client or anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self._model = model

    def reply(self, context: str, user_message: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Contexto (datos reales ya conocidos de Blackboard):\n{context}\n\n"
                        f"Mensaje del estudiante: {user_message}"
                    ),
                }
            ],
        )
        return "".join(block.text for block in response.content if block.type == "text")
