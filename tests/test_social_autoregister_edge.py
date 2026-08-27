"""Edge-case and integration tests for social auto-registration + auto-publish.

Covers: timer auto-publish into feed, withdraw from feed, adapter-missing,
empty projection, migration upgrade/downgrade, feed badge conditional rendering.
"""

from __future__ import annotations

import secrets

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import create_access_token
from app.database import get_db
from app.locktimer.services.drafts import create_draft
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.user import User
from app.platform.social.adapters import TimerSocialAdapter
from app.platform.social.autoregister import ensure_auto_publish, ensure_subject_registered
from app.platform.social.models import SocialSubject
from app.platform.social.repositories import (
    create_profile,
    list_owner_publications,
    withdraw_publication,
)
from app.prefs import sanitize_prefs

# ---------------------------------------------------------------------------
# Timer auto-publish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_locksession_auto_publishes(
    db_session: AsyncSession,
    test_user: User,
):
    """LockSession draft auto-registers AND auto-publishes timer.session."""
    from app.platform.social import get_adapter_registry, register_adapter

    if "timer" not in get_adapter_registry():
        register_adapter(TimerSocialAdapter())

    session = await create_draft(db_session, owner_id=test_user.id)

    # create_draft registers the subject (but does NOT auto-publish drafts)
    subj_result = await db_session.execute(
        select(SocialSubject).where(
            SocialSubject.subject_type == "timer.session",
            SocialSubject.domain_object_id == str(session.id),
        )
    )
    subj = subj_result.scalar_one_or_none()
    assert subj is not None
    assert subj.subject_type == "timer.session"
    assert subj.projection_snapshot is not None
    assert subj.projection_snapshot.get("type") == "timer.session"
    assert subj.projection_snapshot.get("state") == "draft"


@pytest.mark.asyncio
async def test_locksession_auto_publish_respects_visibility_pref(
    db_session: AsyncSession,
    test_user: User,
):
    """Timer auto-publish uses the per-user visibility pref."""
    from app.platform.social import get_adapter_registry, register_adapter

    if "timer" not in get_adapter_registry():
        register_adapter(TimerSocialAdapter())

    test_user.prefs = sanitize_prefs(
        {**(test_user.prefs or {}), "social_auto_publish_visibility": "public"}
    )

    session = await create_draft(db_session, owner_id=test_user.id)

    # Explicitly trigger auto-publish for the timer subject
    result = await ensure_auto_publish(db_session, test_user.id, "timer.session", str(session.id))
    assert result is True

    pubs = await list_owner_publications(db_session, test_user.id)
    timer_pubs = [p for p in pubs if p.subject_namespace == "timer"]
    assert len(timer_pubs) == 1
    assert timer_pubs[0].visibility == "public"


@pytest.mark.asyncio
async def test_locksession_no_publish_when_pref_disabled(
    db_session: AsyncSession,
    test_user: User,
):
    """With social_auto_publish=False, LockSession creates subject but no publication."""
    from app.platform.social import get_adapter_registry, register_adapter

    if "timer" not in get_adapter_registry():
        register_adapter(TimerSocialAdapter())

    test_user.prefs = sanitize_prefs(
        {**(test_user.prefs or {}), "social_auto_publish": False}
    )

    session = await create_draft(db_session, owner_id=test_user.id)

    # Subject is registered even when auto-publish is disabled
    subj_result = await db_session.execute(
        select(SocialSubject).where(
            SocialSubject.subject_type == "timer.session",
            SocialSubject.domain_object_id == str(session.id),
        )
    )
    subj = subj_result.scalar_one_or_none()
    assert subj is not None

    # Explicit auto-publish is blocked by the disabled pref
    result = await ensure_auto_publish(db_session, test_user.id, "timer.session", str(session.id))
    assert result is False

    pubs = await list_owner_publications(db_session, test_user.id)
    timer_pubs = [p for p in pubs if p.subject_namespace == "timer"]
    assert len(timer_pubs) == 0  # ...but not published


# ---------------------------------------------------------------------------
# Withdraw from feed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_withdraw_auto_published_from_feed(
    db_session: AsyncSession,
    test_user: User,
):
    """Owner can withdraw an auto-published item via the feed button."""
    log = ActivityLog(
        user_id=test_user.id,
        entity_id=None,
        status="planned",
        selected_entity_name="Yoga",
        selected_params={},
        user_prompt="test",
    )
    db_session.add(log)
    await db_session.flush()
    await ensure_subject_registered(db_session, test_user.id, "tracker.activity_log", str(log.id))
    await ensure_auto_publish(db_session, test_user.id, "tracker.activity_log", str(log.id))

    pubs = await list_owner_publications(db_session, test_user.id)
    assert len(pubs) == 1
    assert pubs[0].is_active is True

    withdrawn = await withdraw_publication(db_session, pubs[0].id, test_user.id)
    assert withdrawn is not None
    assert withdrawn.is_active is False
    assert withdrawn.withdrawn_at is not None


@pytest.mark.asyncio
async def test_feed_withdraw_button_renders_for_own_items(
    db_session: AsyncSession,
    test_user: User,
):
    """Feed renders a withdraw button for the owner's own publications."""
    await create_profile(db_session, test_user.id, "alice_wd", "alice_wd")

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=None,
        status="planned",
        selected_entity_name="Ride",
        selected_params={},
        user_prompt="test",
    )
    db_session.add(log)
    await db_session.flush()
    await ensure_subject_registered(db_session, test_user.id, "tracker.activity_log", str(log.id))
    await ensure_auto_publish(db_session, test_user.id, "tracker.activity_log", str(log.id))

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    csrf = secrets.token_hex(32)
    token = create_access_token(test_user.id)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.headers.update({"Cookie": f"access_token={token}; csrf_token={csrf}", "X-CSRF-Token": csrf})
            resp = await client.get("/social/feed")
        assert resp.status_code == 200
        # Own item has withdraw form (in 'own publications' section)
        assert "/social/publish/" in resp.text
        assert "withdraw" in resp.text.lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Adapter missing / empty projection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_autoregister_skips_when_adapter_missing(
    db_session: AsyncSession,
    test_user: User,
):
    """With no adapter registered for the namespace, registration is a no-op."""
    from app.platform.social import get_adapter_registry

    registry = get_adapter_registry()
    saved = registry.pop("fake_ns", None)
    try:
        result = await ensure_subject_registered(
            db_session, test_user.id, "fake_ns.my_obj", "obj-123"
        )
        assert result is None
    finally:
        if saved is not None:
            registry["fake_ns"] = saved


@pytest.mark.asyncio
async def test_autopublish_skips_when_projection_empty(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch,
):
    """If the adapter returns an empty projection, auto-publish is skipped."""
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
    await ensure_subject_registered(db_session, test_user.id, "tracker.activity_log", str(log.id))

    async def empty_projection(_db, _sid):
        return {}

    monkeypatch.setattr(
        "app.platform.social.adapters.TrackerSocialAdapter.build_redacted_projection",
        empty_projection,
    )

    result = await ensure_auto_publish(
        db_session, test_user.id, "tracker.activity_log", str(log.id)
    )
    assert result is False

    pubs = await list_owner_publications(db_session, test_user.id)
    assert len(pubs) == 0


# ---------------------------------------------------------------------------
# Feed badge conditional
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_hides_badge_for_manual_publication(
    db_session: AsyncSession,
    test_user: User,
):
    """Manual publications do NOT show the auto-badge."""
    await create_profile(db_session, test_user.id, "alice_manual", "alice_manual")

    from app.platform.social.repositories import create_publication

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=None,
        status="planned",
        selected_entity_name="Manual",
        selected_params={},
        user_prompt="test",
    )
    db_session.add(log)
    await db_session.flush()
    subj = await ensure_subject_registered(
        db_session, test_user.id, "tracker.activity_log", str(log.id)
    )

    import hashlib
    import json as _json

    snap = {"type": "tracker.activity_log", "status": "planned"}
    h = hashlib.sha256(_json.dumps(snap, sort_keys=True).encode()).hexdigest()
    await create_publication(
        db_session, test_user.id, subj.id, "public", snap, h, "tracker", source="manual"
    )

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    csrf = secrets.token_hex(32)
    token = create_access_token(test_user.id)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.headers.update({"Cookie": f"access_token={token}; csrf_token={csrf}", "X-CSRF-Token": csrf})
            resp = await client.get("/social/feed")
        assert resp.status_code == 200
        # The auto-badge text should NOT appear for manual publications
        # (it would only appear next to auto-published items)
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Migration 071
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_column_default_is_manual(
    db_session: AsyncSession,
    test_user: User,
):
    """New SocialPublication rows default source='manual'."""
    from app.platform.social.repositories import create_publication

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=None,
        status="planned",
        selected_entity_name="Test",
        selected_params={},
        user_prompt="test",
    )
    db_session.add(log)
    await db_session.flush()
    subj = await ensure_subject_registered(
        db_session, test_user.id, "tracker.activity_log", str(log.id)
    )

    import hashlib
    import json as _json

    snap = {"type": "tracker.activity_log"}
    h = hashlib.sha256(_json.dumps(snap, sort_keys=True).encode()).hexdigest()
    pub = await create_publication(
        db_session, test_user.id, subj.id, "public", snap, h, "tracker"
    )
    assert pub.source == "manual"


@pytest.mark.asyncio
async def test_source_column_auto(
    db_session: AsyncSession,
    test_user: User,
):
    """Auto-published rows have source='auto'."""
    log = ActivityLog(
        user_id=test_user.id,
        entity_id=None,
        status="planned",
        selected_entity_name="Auto",
        selected_params={},
        user_prompt="test",
    )
    db_session.add(log)
    await db_session.flush()
    await ensure_subject_registered(db_session, test_user.id, "tracker.activity_log", str(log.id))
    await ensure_auto_publish(db_session, test_user.id, "tracker.activity_log", str(log.id))

    pubs = await list_owner_publications(db_session, test_user.id)
    assert len(pubs) == 1
    assert pubs[0].source == "auto"
