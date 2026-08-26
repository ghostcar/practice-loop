"""Tests for SocialSubject auto-registration from domain events (v1.0 S1 bridge).

Covers: idempotent registration, on_task_completed → tracker.activity_log,
locktimer draft → timer.session, timer adapter redaction, publish builds the
snapshot from the adapter (never from client input).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import create_access_token
from app.gamification.handler import on_task_completed
from app.locktimer.services.drafts import create_draft
from app.models.activity_log import ActivityLog
from app.models.locktimer import LockSession
from app.models.user import User
from app.platform.social.adapters import TimerSocialAdapter
from app.platform.social.autoregister import ensure_subject_registered
from app.platform.social.models import SocialSubject


@pytest.mark.asyncio
async def test_ensure_subject_registered_idempotent(
    db_session: AsyncSession,
    test_user: User,
):
    """Registering the same domain object twice yields a single subject row."""
    log = ActivityLog(
        user_id=test_user.id,
        entity_id=None,
        status="planned",
        selected_entity_name="Stretching",
        selected_params={},
        user_prompt="test",
    )
    db_session.add(log)
    await db_session.flush()

    first = await ensure_subject_registered(db_session, test_user.id, "tracker.activity_log", str(log.id))
    assert first is not None

    second = await ensure_subject_registered(db_session, test_user.id, "tracker.activity_log", str(log.id))
    assert second is None  # already registered — no duplicate

    rows = (
        await db_session.execute(
            select(SocialSubject).where(
                SocialSubject.subject_type == "tracker.activity_log",
                SocialSubject.domain_object_id == str(log.id),
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    # Projection built through the tracker adapter (real redacted snapshot).
    assert rows[0].projection_snapshot is not None
    assert rows[0].projection_snapshot.get("type") == "tracker.activity_log"


@pytest.mark.asyncio
async def test_on_task_completed_registers_activity_subject(
    db_session: AsyncSession,
    test_user: User,
):
    """Completing a task auto-registers a tracker.activity_log subject."""
    log = ActivityLog(
        user_id=test_user.id,
        entity_id=None,
        status="planned",
        selected_entity_name="Morning routine",
        selected_params={"intensity": 2},
        user_prompt="test",
    )
    db_session.add(log)
    await db_session.flush()

    await on_task_completed(db_session, test_user.id, log)

    row = (
        await db_session.execute(
            select(SocialSubject).where(
                SocialSubject.subject_type == "tracker.activity_log",
                SocialSubject.domain_object_id == str(log.id),
            )
        )
    ).scalar_one_or_none()
    assert row is not None
    assert row.owner_id == test_user.id
    assert row.projection_snapshot is not None


@pytest.mark.asyncio
async def test_create_draft_registers_timer_subject(
    db_session: AsyncSession,
    test_user: User,
):
    """Creating a locktimer draft auto-registers a timer.session subject."""
    # Ensure the timer adapter is registered (startup registers it only when the
    # SOCIAL_TIMER_ADAPTER_ENABLED flag is on).
    from app.platform.social import get_adapter_registry, register_adapter

    if "timer" not in get_adapter_registry():
        register_adapter(TimerSocialAdapter())

    session = await create_draft(db_session, owner_id=test_user.id)

    row = (
        await db_session.execute(
            select(SocialSubject).where(
                SocialSubject.subject_type == "timer.session",
                SocialSubject.domain_object_id == str(session.id),
            )
        )
    ).scalar_one_or_none()
    assert row is not None
    assert row.owner_id == test_user.id
    assert row.projection_snapshot is not None
    assert row.projection_snapshot.get("type") == "timer.session"


@pytest.mark.asyncio
async def test_timer_adapter_redacts_secrets(
    db_session: AsyncSession,
    test_user: User,
):
    """Timer adapter projection never exposes seed/commitment material."""
    now = datetime.now(UTC)
    session = LockSession(
        owner_id=test_user.id,
        state="draft",
        duration_type="duration_from_start",
        timezone="UTC",
        random_seed_encrypted="super-secret-seed",
        random_seed_commitment="commitment-hash",
        privacy_mode="private",
        created_at=now,
        updated_at=now,
    )
    db_session.add(session)
    await db_session.flush()

    adapter = TimerSocialAdapter()
    projection = await adapter.build_redacted_projection(db_session, str(session.id))

    assert projection.get("state") == "draft"
    assert "random_seed_encrypted" not in projection
    assert "random_seed_commitment" not in projection
    assert "super-secret-seed" not in str(projection)


@pytest.mark.asyncio
async def test_publish_endpoint_builds_snapshot_from_adapter(
    db_session: AsyncSession,
    test_user: User,
):
    """POST /social/publish stores the adapter-built redacted snapshot."""
    from app.database import get_db
    from app.main import app

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=None,
        status="completed",
        selected_entity_name="Stretching",
        selected_params={"intensity": 1},
        user_prompt="test",
        cleaned_response="10 minutes of stretching",
    )
    db_session.add(log)
    await db_session.flush()
    subject = await ensure_subject_registered(db_session, test_user.id, "tracker.activity_log", str(log.id))
    assert subject is not None

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    csrf = secrets.token_hex(32)
    token = create_access_token(test_user.id)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.headers.update({"Cookie": f"access_token={token}; csrf_token={csrf}", "X-CSRF-Token": csrf})
            resp = await client.post(
                "/social/publish",
                data={
                    "subject_id": str(subject.id),
                    "visibility": "public",
                },
            )
        assert resp.status_code == 303, resp.text

        from app.platform.social.models import SocialPublication

        pub = (
            await db_session.execute(
                select(SocialPublication).where(SocialPublication.subject_id == subject.id)
            )
        ).scalar_one()
        assert pub.snapshot.get("type") == "tracker.activity_log"
        assert pub.snapshot.get("status") == "completed"
        assert "cleaned_response" in pub.snapshot
        # The hardcoded client stub must never be stored.
        assert pub.snapshot.get("title") != "Manual publish"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_publish_requires_owned_subject(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """A user cannot publish someone else's subject."""
    from app.database import get_db
    from app.main import app

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=None,
        status="completed",
        selected_entity_name="Owner task",
        selected_params={},
        user_prompt="test",
    )
    db_session.add(log)
    await db_session.flush()
    subject = await ensure_subject_registered(db_session, test_user.id, "tracker.activity_log", str(log.id))
    assert subject is not None

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    csrf = secrets.token_hex(32)
    token = create_access_token(second_user.id)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.headers.update({"Cookie": f"access_token={token}; csrf_token={csrf}", "X-CSRF-Token": csrf})
            resp = await client.post(
                "/social/publish",
                data={"subject_id": str(subject.id), "visibility": "public"},
            )
        assert resp.status_code == 404, resp.text
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_autoregister_noop_when_social_disabled(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch,
):
    """With social disabled the bridge is a silent no-op for domain ops."""
    monkeypatch.setattr("app.config.settings.social_enabled", False)

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=None,
        status="planned",
        selected_entity_name="X",
        selected_params={},
        user_prompt="test",
    )
    db_session.add(log)
    await db_session.flush()

    result = await ensure_subject_registered(db_session, test_user.id, "tracker.activity_log", str(log.id))
    assert result is None
    rows = (
        await db_session.execute(
            select(SocialSubject).where(
                SocialSubject.subject_type == "tracker.activity_log",
                SocialSubject.domain_object_id == str(log.id),
            )
        )
    ).scalars().all()
    assert len(rows) == 0
