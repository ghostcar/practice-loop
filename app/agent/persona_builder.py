"""AI Agent Persona Builder & Prompt Engineering Engine."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona import UserAgentPersona

logger = logging.getLogger(__name__)

PERSONA_PROMPT_PRESETS = {
    "strict_keyholder": "Твой стиль: Строгий Ключник. Требуешь дисциплины и фото-фиксации.",
    "caring_curator": "Твой стиль: Заботливый Куратор. Приоритет — безопасность и Aftercare-восстановление.",
    "endurance_trainer": "Твой стиль: Тренер Выносливости. Мотивируешь к прогрессивным нагрузкам.",
    "anonymous_observer": "Твой стиль: Анонимный Наблюдатель. Даешь сухую аналитику и статистику.",
}


async def get_or_create_user_persona(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> UserAgentPersona:
    """Gets or initializes user AI Agent persona configuration."""
    persona = (
        await db.execute(select(UserAgentPersona).where(UserAgentPersona.user_id == user_id))
    ).scalar_one_or_none()

    if not persona:
        persona = UserAgentPersona(
            user_id=user_id,
            persona_type="caring_curator",
            strictness_level=3,
            tone_of_voice="supportive_formal",
            proactive_frequency="daily",
        )
        db.add(persona)
        await db.flush()

    return persona


async def update_user_persona_config(
    db: AsyncSession,
    user_id: uuid.UUID,
    persona_type: str,
    strictness_level: int,
    tone_of_voice: str,
    proactive_frequency: str,
) -> dict[str, Any]:
    """Updates user AI agent persona parameters."""
    persona = await get_or_create_user_persona(db, user_id)
    persona.persona_type = persona_type
    persona.strictness_level = max(1, min(5, strictness_level))
    persona.tone_of_voice = tone_of_voice
    persona.proactive_frequency = proactive_frequency

    await db.flush()

    prompt_addon = PERSONA_PROMPT_PRESETS.get(persona_type, PERSONA_PROMPT_PRESETS["caring_curator"])

    return {
        "status": "success",
        "user_id": str(user_id),
        "persona_type": persona_type,
        "strictness_level": persona.strictness_level,
        "prompt_addon": prompt_addon,
    }
