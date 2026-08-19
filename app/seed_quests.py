"""Seed catalog quests for gamification challenges (Step 43)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quest import Quest

logger = logging.getLogger(__name__)

SEED_QUESTS: list[dict[str, Any]] = [
    {
        "title": "🧘 Ритм Заботы и Восстановления",
        "description": "Выполнить 3 процедуры ухода за кожей или Aftercare-восстановления подряд.",
        "quest_type": "daily",
        "category": "aftercare",
        "target_count": 3,
        "reward_xp": 150,
        "badge_icon": "routine",
    },
    {
        "title": "🔒 Стальная Дисциплина Chastity",
        "description": "Выполнить 5 своевременных фото-чек-инов замка без просрочек.",
        "quest_type": "weekly",
        "category": "chastity",
        "target_count": 5,
        "reward_xp": 300,
        "badge_icon": "locktimer",
    },
    {
        "title": "🏋️ Идеальный Контур и Осанка",
        "description": "Провести 3 тренировочные сессии удерживания поз.",
        "quest_type": "weekly",
        "category": "training",
        "target_count": 3,
        "reward_xp": 200,
        "badge_icon": "training",
    },
    {
        "title": "📜 Безупречный Договор",
        "description": "Составить и активировать сессию через Конструктор Правил.",
        "quest_type": "streak",
        "category": "consent",
        "target_count": 1,
        "reward_xp": 100,
        "badge_icon": "consent",
    },
]


async def seed_quests(db: AsyncSession) -> int:
    """Seeds default quests if missing."""
    count = 0
    for q_data in SEED_QUESTS:
        existing = (
            await db.execute(select(Quest).where(Quest.title == q_data["title"]))
        ).scalar_one_or_none()
        if not existing:
            quest = Quest(**q_data)
            db.add(quest)
            count += 1

    if count > 0:
        await db.commit()
        logger.info(f"Seeded {count} gamification quests.")
    return count
