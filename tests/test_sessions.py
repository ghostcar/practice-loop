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
async def test_multiple_parallel_sessions_allowed(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Any number of sessions may be created and run in parallel (migration 063)."""
    first = await auth_client.post("/sessions", follow_redirects=False)
    second = await auth_client.post("/sessions", follow_redirects=False)
    assert first.status_code == second.status_code == 303
    sessions = (
        (await db_session.execute(select(ActivitySession).where(ActivitySession.owner_id == test_user.id)))
        .scalars()
        .all()
    )
    assert len(sessions) == 2
    assert {s.status for s in sessions} == {"created"}

    # Both can be started independently and stay active side by side
    for s in sessions:
        resp = await auth_client.post(f"/sessions/{s.id}/start", follow_redirects=False)
        assert resp.status_code == 303
    refreshed = (
        (await db_session.execute(select(ActivitySession).where(ActivitySession.owner_id == test_user.id)))
        .scalars()
        .all()
    )
    assert {s.status for s in refreshed} == {"active"}


@pytest.mark.asyncio
async def test_json_create_multiple_sessions(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """JSON endpoint creates a fresh session each time (parallel sessions allowed)."""
    first = await auth_client.post("/api/v2/sessions", json={"title": "API session"})
    assert first.status_code == 201

    second = await auth_client.post("/api/v2/sessions", json={"title": "Another"})
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["title"] == "Another"

    sessions = (
        (await db_session.execute(select(ActivitySession).where(ActivitySession.owner_id == test_user.id)))
        .scalars()
        .all()
    )
    assert len(sessions) == 2
    assert {s.title for s in sessions} == {"API session", "Another"}


@pytest.mark.asyncio
async def test_create_after_ending_previous(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Ending the open session frees the slot for a new one."""
    await auth_client.post("/sessions", follow_redirects=False)
    session = (
        await db_session.execute(select(ActivitySession).where(ActivitySession.owner_id == test_user.id))
    ).scalar_one()
    await auth_client.post(f"/sessions/{session.id}/end", follow_redirects=False)

    resp = await auth_client.post("/sessions", follow_redirects=False)
    assert resp.status_code == 303
    sessions = (
        (await db_session.execute(select(ActivitySession).where(ActivitySession.owner_id == test_user.id)))
        .scalars()
        .all()
    )
    assert {s.status for s in sessions} == {"ended", "created"}


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


@pytest.mark.asyncio
async def test_json_session_full_lifecycle(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    task = ActivityLog(user_id=test_user.id, selected_entity_name="API task")
    db_session.add(task)
    await db_session.flush()

    created = await auth_client.post("/api/v2/sessions", json={"title": "API session"})
    assert created.status_code == 201
    session_id = created.json()["id"]

    attached = await auth_client.post(f"/api/v2/sessions/{session_id}/tasks", json={"task_id": str(task.id)})
    assert attached.status_code == 200
    assert str(task.id) in attached.json()["task_ids"]

    accepted = await auth_client.post(f"/api/v2/sessions/{session_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["accepted_at"]
    started = await auth_client.post(f"/api/v2/sessions/{session_id}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "active"
    ended = await auth_client.post(f"/api/v2/sessions/{session_id}/end")
    assert ended.status_code == 200
    assert ended.json()["status"] == "ended"

    history = await auth_client.get(f"/api/v2/sessions/{session_id}/history")
    assert history.status_code == 200
    assert [item["event_type"] for item in history.json()] == ["created", "task_added", "accepted", "started", "ended"]


@pytest.mark.asyncio
async def test_live_complete_requires_owned_active_session(
    auth_client: AsyncClient, db_session: AsyncSession, test_user
):
    """Test live completion transitions active session to completed and prevents double XP farming (Audit A-01/A-16)."""
    # 1. Create and start a session
    sess = ActivitySession(owner_id=test_user.id, title="Active Live Session", status="active")
    db_session.add(sess)
    await db_session.commit()

    prog_before = await (
        await db_session.execute(select(UserProgress).where(UserProgress.user_id == test_user.id))
    ).scalar_one_or_none()
    xp_before = prog_before.xp if prog_before else 0

    # 2. Call live complete
    resp = await auth_client.post(
        "/sessions/live/complete",
        data={"session_id": str(sess.id), "notes": "Completed test hold"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    # 3. Assert session status changed to canonical 'ended'
    await db_session.refresh(sess)
    assert sess.status == "ended"

    prog_after = await (
        await db_session.execute(select(UserProgress).where(UserProgress.user_id == test_user.id))
    ).scalar_one_or_none()
    assert prog_after.xp == xp_before + 50

    # 4. Replay attack attempt — calling complete again should NOT award more XP
    resp2 = await auth_client.post(
        "/sessions/live/complete",
        data={"session_id": str(sess.id), "notes": "Replay attempt"},
        follow_redirects=False,
    )
    assert resp2.status_code == 303

    prog_after_replay = await (
        await db_session.execute(select(UserProgress).where(UserProgress.user_id == test_user.id))
    ).scalar_one_or_none()
    assert prog_after_replay.xp == xp_before + 50  # XP unchanged!
