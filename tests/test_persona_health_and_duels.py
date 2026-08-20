"""Integration tests for AI Persona Builder, Health Dashboard, Equipment Maintenance, and Weekly Duels."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.equipment_maintenance import schedule_equipment_maintenance_reminders
from app.agent.persona_builder import get_or_create_user_persona, update_user_persona_config
from app.agent.weekly_duels import create_weekly_user_duel, process_duel_scores_and_determine_winner
from app.models.user import User


@pytest.mark.asyncio
async def test_user_agent_persona_creation_and_config(db_session: AsyncSession, test_user: User):
    """Verify getting and updating AI agent persona configuration."""
    persona = await get_or_create_user_persona(db_session, test_user.id)
    assert persona.persona_type == "caring_curator"

    updated = await update_user_persona_config(
        db_session,
        test_user.id,
        persona_type="strict_keyholder",
        strictness_level=4,
        tone_of_voice="strict_command",
        proactive_frequency="high",
    )
    assert updated["status"] == "success"
    assert updated["persona_type"] == "strict_keyholder"
    assert updated["strictness_level"] == 4


@pytest.mark.asyncio
async def test_persona_builder_page_rendering(auth_client: AsyncClient, test_user: User):
    """GET /agent/persona-builder renders persona builder page."""
    resp = await auth_client.get("/agent/persona-builder")
    assert resp.status_code == 200
    assert "Конструктор Персоны ИИ-Агента" in resp.text


@pytest.mark.asyncio
async def test_health_dashboard_page_rendering(auth_client: AsyncClient, test_user: User):
    """GET /health/dashboard renders health dashboard page."""
    resp = await auth_client.get("/health/dashboard")
    assert resp.status_code == 200
    assert "Дашборд Здоровья и Циклов" in resp.text


@pytest.mark.asyncio
async def test_schedule_equipment_maintenance_reminders(db_session: AsyncSession, test_user: User):
    """Verify scanning equipment logs and scheduling maintenance reminders."""
    maint_res = await schedule_equipment_maintenance_reminders(db_session, test_user)
    assert maint_res["status"] == "success"
    assert len(maint_res["reminders"]) >= 1


@pytest.mark.asyncio
async def test_create_and_process_weekly_user_duel(db_session: AsyncSession, test_user: User):
    """Verify creating weekly 1-on-1 duel and evaluating winner."""
    duel = await create_weekly_user_duel(db_session, challenger_id=test_user.id, opponent_id=test_user.id)
    assert duel.status == "active"

    winner_res = await process_duel_scores_and_determine_winner(db_session, duel.id)
    assert winner_res["status"] == "completed"
    assert winner_res["winner_id"] == str(test_user.id)
