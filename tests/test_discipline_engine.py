"""Unit and integration tests for Unified Cross-Contour Discipline Engine (ADR-206)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.prefs import sanitize_prefs
from app.services.discipline_engine import (
    calc_effective_multiplier,
    get_adjusted_intensity,
    get_user_discipline_state,
    record_clean_check,
    record_violation,
    scale_task_parameters,
)


def test_effective_multiplier_scale(test_user: User):
    """Verify 6 steps (levels 0..5 -> multipliers 1.0 to 6.0) and compound base multiplier."""
    # Standard base (1.0)
    test_user.prefs = sanitize_prefs({"discipline_level": 0, "base_severity_multiplier": 1.0})
    assert calc_effective_multiplier(test_user) == 1.0

    test_user.prefs = sanitize_prefs({"discipline_level": 1, "base_severity_multiplier": 1.0})
    assert calc_effective_multiplier(test_user) == 2.0

    test_user.prefs = sanitize_prefs({"discipline_level": 2, "base_severity_multiplier": 1.0})
    assert calc_effective_multiplier(test_user) == 3.0

    test_user.prefs = sanitize_prefs({"discipline_level": 5, "base_severity_multiplier": 1.0})
    assert calc_effective_multiplier(test_user) == 6.0

    # Hardcore base (> 2.0, e.g. 2.5)
    test_user.prefs = sanitize_prefs({"discipline_level": 2, "base_severity_multiplier": 2.5})
    # 2.5 * (2 + 1) = 7.5
    assert calc_effective_multiplier(test_user) == 7.5


def test_adjusted_intensity_shifts():
    """Verify that every 2 levels shift intensity by one notch (English and Russian)."""
    # Levels 0, 1 -> no shift
    assert get_adjusted_intensity("light", 0) == "light"
    assert get_adjusted_intensity("light", 1) == "light"
    assert get_adjusted_intensity("слабая", 0) == "слабая"

    # Levels 2, 3 -> +1 shift
    assert get_adjusted_intensity("light", 2) == "medium"
    assert get_adjusted_intensity("medium", 3) == "strong"
    assert get_adjusted_intensity("слабая", 2) == "средняя"
    assert get_adjusted_intensity("средняя", 3) == "сильная"

    # Levels 4, 5 -> +2 shift
    assert get_adjusted_intensity("light", 4) == "strong"
    assert get_adjusted_intensity("medium", 5) == "severe"
    assert get_adjusted_intensity("слабая", 4) == "сильная"
    assert get_adjusted_intensity("сильная", 5) == "экстремальная"


@pytest.mark.asyncio
async def test_violation_escalation_and_streak_reset(db_session: AsyncSession, test_user: User):
    """Violations escalate level and reset recovery streak."""
    test_user.prefs = sanitize_prefs({"discipline_level": 1, "recovery_streak": 3})
    db_session.add(test_user)
    await db_session.commit()

    res = await record_violation(db_session, test_user, reason="Late checkin")
    assert res["previous_level"] == 1
    assert res["new_level"] == 2
    assert res["recovery_streak"] == 0

    state = get_user_discipline_state(test_user)
    assert state["discipline_level"] == 2
    assert state["recovery_streak"] == 0


@pytest.mark.asyncio
async def test_stepwise_redemption_thresholds(db_session: AsyncSession, test_user: User):
    """Redemption from Level L to L-1 requires L * 2 consecutive clean checks."""
    # Level 1 -> requires 2 checks
    test_user.prefs = sanitize_prefs({"discipline_level": 1, "recovery_streak": 0})
    db_session.add(test_user)
    await db_session.commit()

    # Check 1: streak becomes 1, no demotion
    res1 = await record_clean_check(db_session, test_user)
    assert res1["level"] == 1
    assert res1["streak"] == 1
    assert res1["demoted"] is False

    # Check 2: streak reaches 2 -> demoted to Level 0, streak resets
    res2 = await record_clean_check(db_session, test_user)
    assert res2["level"] == 0
    assert res2["streak"] == 0
    assert res2["demoted"] is True

    # Level 3 -> requires 6 checks
    test_user.prefs = sanitize_prefs({"discipline_level": 3, "recovery_streak": 5})
    db_session.add(test_user)
    await db_session.commit()

    # 6th check demotes from level 3 to level 2
    res3 = await record_clean_check(db_session, test_user)
    assert res3["level"] == 2
    assert res3["streak"] == 0
    assert res3["demoted"] is True


def test_scale_task_parameters_routine_toggle(test_user: User):
    """Routine tasks only scale if escalation_affects_routine_tasks is True; lock tasks always scale."""
    test_user.prefs = sanitize_prefs({
        "discipline_level": 2,  # multiplier x3.0
        "escalation_affects_routine_tasks": False,
    })

    params = {"reps": 10, "intensity": "light"}

    # 1. Routine task, toggle False -> no scaling
    scaled_routine = scale_task_parameters(test_user, None, params, is_routine=True, in_lock_session=False)
    assert scaled_routine["reps"] == 10
    assert scaled_routine["intensity"] == "light"

    # 2. Lock session task -> always scales
    scaled_lock = scale_task_parameters(test_user, None, params, is_routine=False, in_lock_session=True)
    assert scaled_lock["reps"] == 30
    assert scaled_lock["intensity"] == "medium"

    # 3. Routine task with toggle True -> scales
    test_user.prefs = sanitize_prefs({
        "discipline_level": 2,
        "escalation_affects_routine_tasks": True,
    })
    scaled_routine_enabled = scale_task_parameters(test_user, None, params, is_routine=True, in_lock_session=False)
    assert scaled_routine_enabled["reps"] == 30
    assert scaled_routine_enabled["intensity"] == "medium"


@pytest.mark.asyncio
async def test_settings_page_and_save_discipline(auth_client, test_user, db_session):
    """Verify /settings GET renders discipline fields and POST persists base multiplier and toggle."""
    # GET /settings
    res = await auth_client.get("/settings?tab=modules")
    assert res.status_code == 200
    assert "Сквозной дисциплинарный контур" in res.text

    # POST /settings
    post_data = {
        "theme_choice": "dark",
        "accent": "ember",
        "density": "comfortable",
        "block_order": "header,stats",
        "block_hidden": "",
        "discretion_mode": "off",
        "discretion_start": "22:00",
        "discretion_end": "07:00",
        "blur": 0,
        "llm_mode": "safe",
        "reminder_time": "",
        "reminder_tz": "",
        "tab": "modules",
        "med_gamification": "off",
        "base_severity_multiplier": 2.5,
        "escalation_affects_routine_tasks": "on",
    }
    save_res = await auth_client.post("/settings", data=post_data, follow_redirects=False)
    assert save_res.status_code in (200, 303)

    await db_session.refresh(test_user)
    prefs = test_user.prefs or {}
    assert prefs.get("base_severity_multiplier") == 2.5
    assert prefs.get("escalation_affects_routine_tasks") is True
