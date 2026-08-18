"""Tests for accepted ActivitySession lifecycle and composition audit."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.progress import UserProgress
from app.models.session import ActivitySession
from app.models.session_history import ActivitySessionHistory


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
    assert session.accepted_at is not None


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
    assert response.status_code == 404

    await db_session.refresh(session)
    assert session.status == "created"


@pytest.mark.asyncio
async def test_accept_is_idempotent_and_audited(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    session = ActivitySession(owner_id=test_user.id, status="created")
    db_session.add(session)
    await db_session.flush()

    first = await auth_client.post(f"/sessions/{session.id}/accept", follow_redirects=False)
    second = await auth_client.post(f"/sessions/{session.id}/accept", follow_redirects=False)
    assert first.status_code == second.status_code == 303
    await db_session.refresh(session)
    assert session.accepted_at is not None
    events = (
        (
            await db_session.execute(
                select(ActivitySessionHistory).where(
                    ActivitySessionHistory.session_id == session.id,
                    ActivitySessionHistory.event_type == "accepted",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1


@pytest.mark.asyncio
async def test_task_changes_free_before_accept_and_penalized_after(
    auth_client: AsyncClient, db_session: AsyncSession, test_user
):
    session = ActivitySession(owner_id=test_user.id, status="created", session_rules={"change_penalty_xp": 7})
    first = ActivityLog(user_id=test_user.id, selected_entity_name="First")
    second = ActivityLog(user_id=test_user.id, selected_entity_name="Second")
    progress = UserProgress(user_id=test_user.id, xp=20, combo_count=3)
    db_session.add_all([session, first, second, progress])
    await db_session.flush()

    before = await auth_client.post(
        f"/sessions/{session.id}/tasks/attach", data={"task_id": str(first.id)}, follow_redirects=False
    )
    assert before.status_code == 303
    await db_session.refresh(progress)
    assert progress.xp == 20

    await auth_client.post(f"/sessions/{session.id}/accept", follow_redirects=False)
    after = await auth_client.post(
        f"/sessions/{session.id}/tasks/attach", data={"task_id": str(second.id)}, follow_redirects=False
    )
    assert after.status_code == 303
    await db_session.refresh(progress)
    assert progress.xp == 13
    assert progress.combo_count == 0
    assert progress.total_interrupted == 1

    detach = await auth_client.post(f"/sessions/{session.id}/tasks/{first.id}/detach", follow_redirects=False)
    assert detach.status_code == 303
    await db_session.refresh(progress)
    assert progress.xp == 6
    penalties = (
        (
            await db_session.execute(
                select(ActivitySessionHistory.penalty_xp).where(ActivitySessionHistory.session_id == session.id)
            )
        )
        .scalars()
        .all()
    )
    assert penalties.count(7) == 2


@pytest.mark.asyncio
async def test_ended_session_composition_is_frozen(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    session = ActivitySession(
        owner_id=test_user.id,
        status="ended",
        accepted_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
    )
    task = ActivityLog(user_id=test_user.id, selected_entity_name="Task")
    db_session.add_all([session, task])
    await db_session.flush()

    response = await auth_client.post(
        f"/sessions/{session.id}/tasks/attach", data={"task_id": str(task.id)}, follow_redirects=False
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_sessions_page_shows_tasks_and_audit(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    session = ActivitySession(owner_id=test_user.id, status="created", accepted_at=datetime.now(UTC))
    task = ActivityLog(user_id=test_user.id, session=session, selected_entity_name="Audited task")
    db_session.add_all([session, task])
    await db_session.flush()
    db_session.add(
        ActivitySessionHistory(
            session_id=session.id,
            actor_id=test_user.id,
            event_type="task_added",
            details={"title": "Audited task"},
            penalty_xp=10,
        )
    )
    await db_session.flush()

    response = await auth_client.get("/sessions")
    assert response.status_code == 200
    assert "Audited task" in response.text
    assert "Audit history" in response.text
    assert "-10 XP" in response.text
