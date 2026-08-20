"""Pre-Session Readiness & Physical Stress Testing Engine."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def evaluate_pre_session_readiness(
    answers: list[int],
) -> dict[str, Any]:
    """Calculates physical & mental readiness score (0..100) from 5 diagnostic questions."""
    if not answers:
        return {"status": "error", "reason": "no_answers_provided"}

    # Average 1..5 scale converted to 0..100%
    avg_score = sum(answers) / len(answers)
    readiness_percentage = max(0.0, min(100.0, (avg_score / 5.0) * 100.0))

    is_load_restricted = readiness_percentage < 30.0

    recommendations = []
    if is_load_restricted:
        recommendations.append("⚠️ ВНИМАНИЕ: Уровень готовности критически низок (< 30%).")
        recommendations.append("ИИ рекомендует снизить интенсивность на 50% или заменить сессию на Aftercare-отдых.")
    else:
        recommendations.append("✅ Физическое состояние в норме. Нагрузка допущена без ограничений.")

    return {
        "status": "success",
        "readiness_score": readiness_percentage,
        "is_load_restricted": is_load_restricted,
        "recommendations": recommendations,
    }
