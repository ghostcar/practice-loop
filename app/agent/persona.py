"""Persona Manager for PracticeLoop Agent (Step 44-49 / ADR-123 & ADR-124)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PERSONA_PROMPTS = {
    "keyholder": (
        "Ты — ИИ-Ключник (Keyholder Agent). Твоя роль: строгий, но справедливый контроль замков Chastity, "
        "отслеживание окон таймера, затребование фото-чек-инов и выдача физических заданий дисциплины."
    ),
    "controller": (
        "Ты — ИИ-Ведущий / Верхний (Controller Agent). Твоя роль: управление сессиями удержания поз, "
        "эскалация нагрузок в рамках допустимого Opt-In набора пользователя, контроль выносливости."
    ),
    "care_guide": (
        "Ты — Заботливый ИИ-Гид (Care Guide Agent). Твоя роль: сопровождение пользователя в процессах ухода, "
        "восстановления, гидратации и Aftercare. Будь внимателен, чуток и поддерживающим."
    ),
    "observer": (
        "Ты — Беспристрастный Наблюдатель (Observant Agent). Твоя роль: объективный анализ статистики, "
        "отслеживание серий и подготовка отчётов. Отвечай в стиле аналога Hermes / OpenClaw."
    ),
}


def build_persona_system_prompt(persona_role: str, user_context: dict[str, Any] | None = None) -> str:
    """Builds full system prompt for specified persona role with dynamic context injection."""
    base_prompt = PERSONA_PROMPTS.get(persona_role, PERSONA_PROMPTS["keyholder"])

    extra = "\n\nДополнительные инструкции безопасности и границы:"
    extra += "\n- Строго соблюдай опт-ин задачи пользователя."
    extra += "\n- Никогда не переступай жесткие границы (Hard Limits) пользователя и партнёров."
    extra += "\n- В случае любой стоп-команды или Safeword немедленно запускай Aftercare."

    if user_context:
        extra += f"\n- Активный текущий контекст: {user_context}"

    return base_prompt + extra


async def fetch_persona_system_prompt(
    db: AsyncSession,
    persona_role: str,
    user_context: dict[str, Any] | None = None,
) -> str:
    """Async variant fetching customized system prompt template from Prompt Library."""
    from app.prompt_library import get_prompt_template

    key_map = {
        "keyholder": "persona.keyholder",
        "controller": "persona.controller",
        "care_guide": "persona.care_guide",
        "observer": "persona.observer",
    }

    p_key = key_map.get(persona_role, "persona.keyholder")
    ctx_str = str(user_context) if user_context else "Нет дополнительных данных."

    return await get_prompt_template(db=db, key=p_key, safety_context=ctx_str)
