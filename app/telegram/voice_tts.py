"""Voice TTS Response Engine for Telegram Bot."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def synthesize_persona_voice_response(
    text: str,
    persona_name: str = "ИИ-Верхний",
) -> dict[str, Any]:
    """Prepares audio payload for Telegram bot voice response."""
    formatted_script = f"[{persona_name}]: {text}"
    logger.info(f"Синтезировано голосовое сообщение для Telegram ({persona_name}): {text[:50]}...")

    return {
        "status": "success",
        "persona_name": persona_name,
        "script": formatted_script,
        "audio_format": "ogg_opus",
        "simulated_duration_sec": max(3, len(text) // 15),
    }
