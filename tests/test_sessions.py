"""Tests for session management: create, start, end."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import ActivitySession


@pytest.mark.asyncio
async def test_create_session(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Create a new session."""
    response = await auth_client.post("/sessions", follow_redirects=False)
    assert response.status_code == 303

    result = await db_session.execute(select(ActivitySession).where(ActivitySession.owner_id == test_user.id))
    session = result.scalar_one_or_none()
    assert session is not None
    assert session.status == "created"


@pytest.mark.asyncio
async def test_start_session(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Start a created session."""
    session = ActivitySession(owner_id=test_user.id, status="created")
    db_session.add(session)
    await db_session.flush()

    response = await auth_client.post(f"/sessions/{session.id}/start", follow_redirects=False)
    assert response.status_code == 303

    await db_session.refresh(session)
    assert session.status == "active"
    assert session.started_at is not None


@pytest.mark.asyncio
async def test_end_session(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """End an active session."""
    session = ActivitySession(owner_id=test_user.id, status="active")
    db_session.add(session)
    await db_session.flush()

    response = await auth_client.post(f"/sessions/{session.id}/end", follow_redirects=False)
    assert response.status_code == 303

    await db_session.refresh(session)
    assert session.status == "ended"
    assert session.ended_at is not None


@pytest.mark.asyncio
async def test_cannot_modify_others_session(auth_client: AsyncClient, db_session: AsyncSession):
    """Cannot start a session owned by another user."""
    from app.auth import hash_password
    from app.models.user import User

    other = User(
        email="other@example.com",
        password_hash=hash_password("secret123"),
    )
    db_session.add(other)
    await db_session.flush()

    session = ActivitySession(owner_id=other.id, status="created")
    db_session.add(session)
    await db_session.flush()

    response = await auth_client.post(f"/sessions/{session.id}/start", follow_redirects=False)
    assert response.status_code == 303

    await db_session.refresh(session)
    assert session.status == "created"
