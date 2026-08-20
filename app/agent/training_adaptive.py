"""Dynamic Adaptive Training Evaluator & Manager (Step 54 / ADR-125)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adaptive_training import AdaptiveProgram, AdaptiveProgramStep

logger = logging.getLogger(__name__)


async def create_adaptive_program(
    user_id: uuid.UUID,
    title: str,
    focus_domain: str,
    total_days: int,
    difficulty_level: int,
    db: AsyncSession,
) -> AdaptiveProgram:
    """Creates a new adaptive training program and populates initial steps."""
    program = AdaptiveProgram(
        user_id=user_id,
        title=title,
        focus_domain=focus_domain,
        total_days=total_days,
        difficulty_level=difficulty_level,
        status="active",
    )
    db.add(program)
    await db.flush()

    # Generate initial baseline steps
    for day_num in range(1, total_days + 1):
        target_minutes = 30 + (day_num - 1) * 10
        step_title = f"День {day_num}: {title} ({target_minutes} мин)"
        step = AdaptiveProgramStep(
            program_id=program.id,
            day_number=day_num,
            title=step_title,
            target_parameters={"target_hold_minutes": target_minutes, "hydration_ml": 500},
            status="pending",
        )
        db.add(step)

    await db.commit()
    return program


async def log_step_feedback_and_adapt(
    step_id: uuid.UUID,
    comfort_score: int,
    actual_minutes: int,
    notes: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """Logs user feedback for step and dynamically adapts upcoming steps via Agent rules."""
    step = (await db.execute(select(AdaptiveProgramStep).where(AdaptiveProgramStep.id == step_id))).scalar_one_or_none()

    if not step:
        return {"status": "error", "message": "Step not found."}

    step.actual_feedback = {
        "comfort_score": comfort_score,
        "actual_minutes": actual_minutes,
        "notes": notes,
    }
    step.status = "completed"

    # Agent Adaptive Adjustment Logic
    upcoming_steps = (
        (
            await db.execute(
                select(AdaptiveProgramStep)
                .where(
                    AdaptiveProgramStep.program_id == step.program_id,
                    AdaptiveProgramStep.day_number > step.day_number,
                    AdaptiveProgramStep.status == "pending",
                )
                .order_by(AdaptiveProgramStep.day_number)
            )
        )
        .scalars()
        .all()
    )

    adjustment_summary = ""
    if comfort_score >= 4:
        # Ramp-Up: Increase target hold time for upcoming days
        for upcoming in upcoming_steps:
            curr_target = upcoming.target_parameters.get("target_hold_minutes", 30)
            upcoming.target_parameters["target_hold_minutes"] = curr_target + 10
            upcoming.title = f"День {upcoming.day_number}: Рамп-Ап (+10 мин)"
            upcoming.ai_adjustment_reason = "Отличный комфорт (score >= 4). ИИ повысил плановую нагрузку."
        adjustment_summary = "ИИ повысил нагрузку на следующие дни на +10 мин."

    elif comfort_score <= 2:
        # Recovery/Deload: Reduce target hold time and insert rest guidance
        for idx, upcoming in enumerate(upcoming_steps):
            if idx == 0:
                upcoming.title = f"День {upcoming.day_number}: День Восстановления & Aftercare"
                upcoming.target_parameters["target_hold_minutes"] = 15
                upcoming.ai_adjustment_reason = "Отмечен дискомфорт. ИИ выделил разгрузочный день ухода."
            else:
                curr_target = upcoming.target_parameters.get("target_hold_minutes", 30)
                upcoming.target_parameters["target_hold_minutes"] = max(15, curr_target - 10)
                upcoming.ai_adjustment_reason = "ИИ снизил планку для стабилизации отклика организма."
        adjustment_summary = "ИИ снизил нагрузку и добавил разгрузочный день восстановления."

    else:
        adjustment_summary = "Нагрузка сохранена на стабильном уровне."

    await db.commit()
    return {
        "status": "success",
        "step_id": str(step_id),
        "comfort_score": comfort_score,
        "adjustment_summary": adjustment_summary,
    }
