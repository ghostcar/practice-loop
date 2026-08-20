"""Tests for Session Wizard Extensions Matrix & Attached Extensions (Steps 86-87)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import ActivitySession


@pytest.mark.asyncio
async def test_session_wizard_extensions_page(auth_client: AsyncClient):
    """GET /sessions/wizard — Session Wizard Page with Extensions Matrix."""
    response = await auth_client.get("/sessions/wizard")
    assert response.status_code == 200
    assert "Модули Расширений Сессии" in response.text


@pytest.mark.asyncio
async def test_create_custom_session_with_extensions(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """POST /sessions/create-custom — Create session with attached Chaster extensions."""
    response = await auth_client.post(
        "/sessions/create-custom",
        data={
            "title": "Extended Session Test",
            "ai_role": "keyholder",
            "notes": "Testing extensions matrix",
            "ext_wheel": "true",
            "ext_pillory": "true",
            "ext_aftercare": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(select(ActivitySession).where(ActivitySession.owner_id == test_user.id))
    session = result.scalars().first()
    assert session is not None
    assert session.session_rules is not None
    assert "extensions" in session.session_rules
    assert session.session_rules["extensions"]["wheel"] is True
    assert session.session_rules["extensions"]["pillory"] is True
