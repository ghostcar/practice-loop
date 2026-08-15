"""Discretion notification masking (DESIGN_V2 §12, ADR-081 debt).

When discretion mode is active, in-app and Telegram notification texts are
neutralized to a localized generic variant — data, rules, safety and audit are
never touched.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification.handler import on_task_completed, on_task_interrupted
from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.notification import Notification
from app.prefs import neutral_notification, prefs_from_dict

# ---------------------------------------------------------------------------
# Unit: neutral_notification helper
# ---------------------------------------------------------------------------


def test_neutral_notification_off():
    prefs = prefs_from_dict({"discretion": {"mode": "off"}})
    assert neutral_notification(prefs, "Title", "Body", "en") == ("Title", "Body")


def test_neutral_notification_always_en():
    prefs = prefs_from_dict({"discretion": {"mode": "always"}})
    title, body = neutral_notification(prefs, "Level Up! 🎉", "You reached level 2", "en")
    assert title == "Update"
    assert body == "Open the app to view details."


def test_neutral_notification_always_ru():
    prefs = prefs_from_dict({"discretion": {"mode": "always"}})
    title, body = neutral_notification(prefs, "X", "Y", "ru")
    assert title == "Обновление"
    assert body == "Откройте приложение, чтобы посмотреть детали."


def test_neutral_notification_none_prefs():
    assert neutral_notification(None, "Title", "Body", "en") == ("Title", "Body")


# ---------------------------------------------------------------------------
# Integration: notification creation honours discretion
# ---------------------------------------------------------------------------


async def _make_log(db: AsyncSession, test_user) -> tuple[Entity, ActivityLog]:
    entity = Entity(
        type="one_time",
        real_name="Test Task",
        category="Test",
        owner_id=test_user.id,
    )
    db.add(entity)
    await db.flush()

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="planned",
        selected_entity_name="Test Task",
    )
    db.add(log)
    await db.flush()
    return entity, log


@pytest.mark.asyncio
async def test_interrupt_masks_penalty_notification_when_discreet(db_session: AsyncSession, test_user):
    test_user.prefs = {"discretion": {"mode": "always"}}
    await db_session.flush()
    _, log = await _make_log(db_session, test_user)

    result = await on_task_interrupted(db_session, test_user.id, log)
    assert result["combo_reset"] is True

    notifs = (
        (await db_session.execute(select(Notification).where(Notification.user_id == test_user.id)))
        .scalars()
        .all()
    )
    assert len(notifs) == 1
    n = notifs[0]
    assert n.type == "penalty"  # type/link preserved — only text masked
    assert n.link == "/tasks/"
    assert n.title == "Update"
    assert n.body == "Open the app to view details."


@pytest.mark.asyncio
async def test_interrupt_keeps_notification_when_not_discreet(db_session: AsyncSession, test_user):
    _, log = await _make_log(db_session, test_user)

    await on_task_interrupted(db_session, test_user.id, log)

    notifs = (
        (await db_session.execute(select(Notification).where(Notification.user_id == test_user.id)))
        .scalars()
        .all()
    )
    assert len(notifs) == 1
    assert notifs[0].title == "Task Interrupted ⚠️"
    assert notifs[0].body.startswith("-")


@pytest.mark.asyncio
async def test_complete_masks_streak_notification_when_discreet(db_session: AsyncSession, test_user):
    test_user.prefs = {"discretion": {"mode": "always"}}
    await db_session.flush()
    _, log = await _make_log(db_session, test_user)

    # Pre-set streak so completion triggers the 3-day milestone notification.
    from app.gamification.handler import get_or_create_progress

    progress = await get_or_create_progress(db_session, test_user.id)
    progress.current_streak = 2
    await db_session.flush()

    await on_task_completed(db_session, test_user.id, log)

    notifs = (
        (await db_session.execute(select(Notification).where(Notification.user_id == test_user.id)))
        .scalars()
        .all()
    )
    streak = [n for n in notifs if n.type == "streak"]
    assert len(streak) == 1
    assert streak[0].title == "Update"
    assert streak[0].body == "Open the app to view details."
