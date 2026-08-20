"""AI Adaptive Training Program Generator."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adaptive_training import AdaptiveProgram, AdaptiveProgramStep
from app.models.care import CareEntry
from app.models.user import User

logger = logging.getLogger(__name__)


async def generate_adaptive_weekly_training_program(
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    """Generates 7-day adaptive training program with progressive loads and rest days."""
    recent_care = (
        await db.execute(
            select(CareEntry).where(CareEntry.user_id == user.id).order_by(CareEntry.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()

    baseline_intensity = 7 if (recent_care and (recent_care.skin_reaction or 3) >= 4) else 4

    program = AdaptiveProgram(
        user_id=user.id,
        title="7-Дневная Адаптивная Программа ИИ",
        focus_domain="adaptive_fitness",
        total_days=7,
        current_day=1,
        difficulty_level=max(1, min(5, baseline_intensity // 2)),
        status="active",
    )
    db.add(program)
    await db.flush()

    steps_data = [
        ("День 1: Втягивающая Разминка", baseline_intensity, "20 мин разминки и растяжки"),
        ("День 2: Базовый Комплекс Нагрузки", baseline_intensity + 1, "30 мин упражнений средней интенсивности"),
        ("День 3: Активное Восстановление & Гидратация", 2, "Лёгкая прогулка и ромашковый чай"),
        ("День 4: Пиковая Интенсивность", min(10, baseline_intensity + 2), "40 мин упражнений высокого темпа"),
        ("День 5: Заботу и Релаксация (Aftercare)", 1, "Сеанс ухода и массаж"),
        ("День 6: Силовой Зачет", baseline_intensity + 1, "35 мин контроля выносливости"),
        ("День 7: Полный День Отдыха", 0, "День восстановления энергии"),
    ]

    for idx, (title, intensity, desc) in enumerate(steps_data, start=1):
        step = AdaptiveProgramStep(
            program_id=program.id,
            day_number=idx,
            title=title,
            target_parameters={"target_intensity": intensity, "instruction": desc},
            status="pending",
        )
        db.add(step)

    await db.flush()

    return {
        "status": "success",
        "program_id": str(program.id),
        "title": program.title,
        "steps_count": len(steps_data),
        "baseline_intensity": baseline_intensity,
    }
