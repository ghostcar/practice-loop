"""Care & Aftercare Protocol Engine v2 for PracticeLoop Agent."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.care import CareEntry
from app.models.user import User

logger = logging.getLogger(__name__)


async def record_aftercare_recovery_protocol(
    db: AsyncSession,
    user: User,
    comfort_level: int,
    stress_score: int,
    notes: str = "",
) -> dict[str, Any]:
    """Logs aftercare metrics and generates AI adaptive recovery recommendations."""
    c_level = max(1, min(10, comfort_level))
    s_score = max(1, min(10, stress_score))

    entry = CareEntry(
        user_id=user.id,
        entry_date=date.today(),
        skin_reaction=5 if c_level >= 7 else 3,
        notes=f"[Aftercare Protocol v2] Комфорт: {c_level}/10 | Стресс: {s_score}/10 | Заметки: {notes}",
    )
    db.add(entry)
    await db.flush()

    recommendations = ["💧 Гидратация: Выпить 750 мл теплой воды / ромашкового чая."]
    if s_score >= 7:
        recommendations.append("🛋️ Покой: 12 часов глубокого отдыха без сильных нагрузок.")
        recommendations.append("🎵 Акустический уход: Легкая медитация или успокаивающая музыка.")

    if c_level <= 5:
        recommendations.append("🧴 Забота о теле: Нанести успокаивающий бальзам / уходовые средства.")
        recommendations.append("🛌 Полный покой: Отменить физические сессии на 24 часа.")

    return {
        "status": "success",
        "entry_id": str(entry.id),
        "comfort_level": c_level,
        "stress_score": s_score,
        "recommendations": recommendations,
        "summary_markdown": (
            f"🛡️ *Протокол Заботы & Восстановления Зафиксирован*\n"
            f"• Уровень Комфорта: *{c_level}/10*\n"
            f"• Уровень Стресса: *{s_score}/10*\n\n"
            f"💡 *Адаптивные Рекомендации ИИ-Агента:*\n" + "\n".join(recommendations)
        ),
    }
