"""Discipline Engine — Unified cross-contour disciplinary escalation & redemption (ADR-206).

Handles:
- 6-step escalation scale (levels 0..5, multiplier x1.0 to x6.0)
- Compound multiplier calculation (base_severity_multiplier * step_multiplier)
- Step-wise redemption: decreasing by 1 level requires 2, 4, 6, 8, 10 consecutive clean checks
- Physical force / intensity shift: every 2 levels shift activity intensity
  (light -> medium -> strong -> severe -> extreme)
- Task parameter scaling: scaling duration, repetition, counts and shifting intensity levels
  (controlled by escalation_affects_routine_tasks flag for routine tasks; always applied inside lock sessions)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.prefs import raw_dict, sanitize_prefs

logger = logging.getLogger(__name__)

INTENSITY_SCALE = ["light", "medium", "strong", "severe", "extreme"]
INTENSITY_MAP_RU = {
    "легкая": "light",
    "легкий": "light",
    "слабая": "light",
    "слабый": "light",
    "средняя": "medium",
    "средний": "medium",
    "умеренная": "medium",
    "умеренный": "medium",
    "сильная": "strong",
    "сильный": "strong",
    "жесткая": "severe",
    "жесткий": "severe",
    "суровая": "severe",
    "суровый": "severe",
    "экстремальная": "extreme",
    "экстремальный": "extreme",
}
INTENSITY_REVERSE_RU = {
    "light": "слабая",
    "medium": "средняя",
    "strong": "сильная",
    "severe": "жесткая",
    "extreme": "экстремальная",
}


def get_user_discipline_state(user: User) -> dict[str, Any]:
    """Extracts discipline-related state from user preferences."""
    prefs = raw_dict(getattr(user, "prefs", None)) or {}
    return {
        "discipline_level": int(prefs.get("discipline_level", 0)),
        "recovery_streak": int(prefs.get("recovery_streak", 0)),
        "base_severity_multiplier": float(prefs.get("base_severity_multiplier", 1.0)),
        "escalation_affects_routine_tasks": bool(prefs.get("escalation_affects_routine_tasks", False)),
    }


def calc_effective_multiplier(user: User) -> float:
    """Calculates total disciplinary multiplier: base_severity_multiplier * (level + 1)."""
    state = get_user_discipline_state(user)
    base = max(1.0, state["base_severity_multiplier"])
    level = max(0, min(5, state["discipline_level"]))
    step_mult = float(level + 1)
    return round(base * step_mult, 2)


def get_adjusted_intensity(base_intensity: str, discipline_level: int) -> str:
    """Every 2 discipline levels shift the intensity upwards by one notch.

    Levels 0, 1 -> shift 0 (no change)
    Levels 2, 3 -> shift +1 (e.g. light -> medium, medium -> strong)
    Levels 4, 5 -> shift +2 (e.g. light -> strong, medium -> severe)
    """
    if not base_intensity:
        return base_intensity

    level = max(0, min(5, discipline_level))
    shift = level // 2
    if shift == 0:
        return base_intensity

    val_lower = base_intensity.strip().lower()
    is_ru = val_lower in INTENSITY_MAP_RU
    canonical = INTENSITY_MAP_RU.get(val_lower, val_lower)

    if canonical not in INTENSITY_SCALE:
        return base_intensity

    idx = INTENSITY_SCALE.index(canonical)
    new_idx = min(len(INTENSITY_SCALE) - 1, idx + shift)
    new_canonical = INTENSITY_SCALE[new_idx]

    if is_ru:
        return INTENSITY_REVERSE_RU.get(new_canonical, new_canonical)
    return new_canonical


async def record_violation(db: AsyncSession, user: User, reason: str = "") -> dict[str, Any]:
    """Records a disciplinary violation: increases discipline level (+1, max 5) and resets streak."""
    prefs = dict(raw_dict(getattr(user, "prefs", None)) or {})
    prev_level = int(prefs.get("discipline_level", 0))
    new_level = min(5, prev_level + 1)

    prefs["discipline_level"] = new_level
    prefs["recovery_streak"] = 0
    user.prefs = sanitize_prefs(prefs)
    db.add(user)
    await db.commit()

    eff_mult = calc_effective_multiplier(user)
    logger.info(
        f"Discipline violation recorded for user {user.id}: level {prev_level} -> {new_level}, "
        f"effective multiplier: {eff_mult}x (reason: {reason})"
    )

    return {
        "previous_level": prev_level,
        "new_level": new_level,
        "multiplier": eff_mult,
        "recovery_streak": 0,
        "reason": reason,
    }


async def record_clean_check(db: AsyncSession, user: User) -> dict[str, Any]:
    """Records a successful clean check / compliance event.

    Redemption requires 2, 4, 6, 8, 10 consecutive clean checks to drop 1 level.
    """
    prefs = dict(raw_dict(getattr(user, "prefs", None)) or {})
    current_level = int(prefs.get("discipline_level", 0))
    current_streak = int(prefs.get("recovery_streak", 0))

    if current_level == 0:
        return {
            "level": 0,
            "streak": current_streak + 1,
            "required_checks": 0,
            "demoted": False,
            "multiplier": calc_effective_multiplier(user),
        }

    new_streak = current_streak + 1
    required_checks = current_level * 2  # Level 1: 2, Level 2: 4, Level 3: 6, Level 4: 8, Level 5: 10
    demoted = False
    new_level = current_level

    if new_streak >= required_checks:
        new_level = max(0, current_level - 1)
        new_streak = 0
        demoted = True

    prefs["discipline_level"] = new_level
    prefs["recovery_streak"] = new_streak
    user.prefs = sanitize_prefs(prefs)
    db.add(user)
    await db.commit()

    eff_mult = calc_effective_multiplier(user)
    return {
        "level": new_level,
        "previous_level": current_level,
        "streak": new_streak,
        "required_checks": required_checks,
        "demoted": demoted,
        "multiplier": eff_mult,
    }


def scale_task_parameters(
    user: User,
    params_schema: dict | None,
    params: dict,
    is_routine: bool = False,
    in_lock_session: bool = False,
) -> dict:
    """Scales task execution parameters according to current discipline escalation.

    - If is_routine is True, scaling applies ONLY if user enabled `escalation_affects_routine_tasks`.
    - If in_lock_session is True, scaling ALWAYS applies regardless of routine toggle.
    - Scales quantitative parameters (reps, count, duration, hits) by effective multiplier.
    - Shifts intensity levels (light -> medium -> strong ...) every 2 levels.
    """
    state = get_user_discipline_state(user)
    if is_routine and not in_lock_session and not state["escalation_affects_routine_tasks"]:
        return dict(params)

    multiplier = calc_effective_multiplier(user)
    level = state["discipline_level"]
    scaled = dict(params)

    numeric_keys = {
        "reps", "count", "duration", "duration_minutes", "hits", "strikes",
        "repetitions", "punishment_count", "hold_seconds", "quantity",
    }
    intensity_keys = {"intensity", "force", "power", "strength", "difficulty"}

    schema_properties = (params_schema or {}).get("properties", {})

    for k, v in list(scaled.items()):
        key_lower = k.lower()
        if key_lower in numeric_keys and isinstance(v, (int, float)):
            new_val = v * multiplier
            if isinstance(v, int):
                new_val = int(round(new_val))
            prop_schema = schema_properties.get(k, {})
            max_val = prop_schema.get("maximum")
            if max_val is not None:
                new_val = min(new_val, max_val * 2)
            scaled[k] = new_val
        elif key_lower in intensity_keys and isinstance(v, str):
            scaled[k] = get_adjusted_intensity(v, level)

    return scaled
