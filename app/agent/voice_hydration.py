"""Voice Log STT Auto-Hydration Engine for PracticeLoop Agent."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.user import User

logger = logging.getLogger(__name__)


async def parse_transcript_with_llm(transcript_text: str) -> dict[str, Any]:
    """Fallback / heuristic parser for transcript text into structured domain entities."""
    text_lower = transcript_text.lower()

    tasks_completed = []
    tasks_interrupted = []
    measurements = {}

    if "выполнил" in text_lower or "сделал" in text_lower or "прошел" in text_lower:
        tasks_completed.append("Голосовая Практика")

    if "пропустил" in text_lower or "не сделал" in text_lower or "прервал" in text_lower:
        tasks_interrupted.append("Пропущенная Практика")

    if "вода" in text_lower or "воды" in text_lower or "выпил" in text_lower:
        measurements["water_ml"] = 500.0

    if "сон" in text_lower or "поспал" in text_lower or "часов" in text_lower:
        measurements["sleep_hours"] = 8.0

    if "настроение" in text_lower:
        measurements["mood_score"] = 9.0

    return {
        "raw_transcript": transcript_text,
        "tasks_completed": tasks_completed,
        "tasks_interrupted": tasks_interrupted,
        "measurements": measurements,
    }


async def process_voice_transcript_intake(
    db: AsyncSession,
    user: User,
    transcript_text: str,
) -> dict[str, Any]:
    """Processes transcribed voice text, creates logs in DB, and returns markdown summary."""
    parsed = await parse_transcript_with_llm(transcript_text)
    logs_created = []

    for task_name in parsed.get("tasks_completed", []):
        log = ActivityLog(
            user_id=user.id,
            status="completed",
            user_prompt=f"[Voice Intake] {task_name}",
            cleaned_response=transcript_text,
        )
        db.add(log)
        logs_created.append(f"✅ Выполнено: {task_name}")

    for task_name in parsed.get("tasks_interrupted", []):
        log = ActivityLog(
            user_id=user.id,
            status="interrupted",
            user_prompt=f"[Voice Intake] {task_name}",
            cleaned_response=transcript_text,
        )
        db.add(log)
        logs_created.append(f"⚠️ Прервано: {task_name}")

    measurements = parsed.get("measurements", {})
    if measurements:
        m_items = [f"• {k}: {v}" for k, v in measurements.items()]
        logs_created.append("📊 Метрики здоровья:\n" + "\n".join(m_items))

    await db.flush()

    summary_lines = [
        f"🎙️ *Голосовая заметка обработана ИИ-Агентом:*\n_{transcript_text}_",
        "",
        "📋 *Зафиксированные записи:*",
    ]
    if logs_created:
        summary_lines.extend(logs_created)
    else:
        summary_lines.append("📝 Текст сохранен в дневник заметок.")

    return {
        "status": "success",
        "raw_transcript": transcript_text,
        "summary_markdown": "\n".join(summary_lines),
        "logs_count": len(logs_created),
    }
