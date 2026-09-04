"""Integration tests for Analytics Graph, AI Training Generator, and Safety Auditor."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.safety_auditor import audit_user_safety_and_burnout
from app.agent.training_generator import generate_adaptive_weekly_training_program
from app.models.activity_log import ActivityLog
from app.models.user import User


@pytest.mark.asyncio
async def test_analytics_graph_page_rendering(auth_client: AsyncClient, test_user: User):
    """GET /analytics/graph returns 200 OK and renders correlation nodes."""
    resp = await auth_client.get("/analytics/graph")
    assert resp.status_code == 200
    assert "Интерактивный Граф Взаимосвязей" in resp.text


@pytest.mark.asyncio
async def test_generate_adaptive_weekly_training_program(db_session: AsyncSession, test_user: User):
    """Verify AI generates 7-day adaptive training program."""
    res = await generate_adaptive_weekly_training_program(db_session, test_user)
    assert res["status"] == "success"
    assert res["steps_count"] == 7
    assert "7-Дневная Адаптивная Программа ИИ" in res["title"]


@pytest.mark.asyncio
async def test_audit_user_safety_and_burnout_triggers_freeze(db_session: AsyncSession, test_user: User):
    """Verify safety auditor triggers protective freeze on high fatigue."""
    for _ in range(3):
        db_session.add(ActivityLog(user_id=test_user.id, status="interrupted"))
    await db_session.flush()

    audit_res = await audit_user_safety_and_burnout(db_session, test_user)
    assert audit_res["status"] == "success"
    assert audit_res["burnout_score"] >= 70.0
    assert audit_res["is_freeze_triggered"] is True
    assert len(audit_res["safety_notes"]) >= 1
