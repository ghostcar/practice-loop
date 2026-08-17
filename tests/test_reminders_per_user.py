"""Per-user reminder schedule tests (Шаг 17f, ADR-098).

Covers the ``prefs.reminder_time``/``prefs.reminder_tz`` fields (inherit the
global default when empty/invalid) and ``run_reminder_cycle_for_user`` running
a single-user daily cycle in the user's own timezone.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import Medication, MedSchedule
from app.models.notification import Notification
from app.models.user import User
from app.prefs import prefs_from_dict, sanitize_prefs


def test_prefs_reminder_fields_valid() -> None:
    p = prefs_from_dict({"reminder_time": "08:30", "reminder_tz": "Europe/Moscow"})
    assert p.reminder_time == "08:30"
    assert p.reminder_tz == "Europe/Moscow"


def test_prefs_reminder_fields_inherit_on_empty_or_invalid() -> None:
    # empty → inherit (empty string, resolved against settings at use-site)
    assert prefs_from_dict({}).reminder_time == ""
    assert prefs_from_dict({}).reminder_tz == ""
    # invalid HH:MM / invalid IANA name → fall back to inherit
    p = prefs_from_dict({"reminder_time": "25:99", "reminder_tz": "Not/AZone"})
    assert p.reminder_time == ""
    assert p.reminder_tz == ""


def test_prefs_reminder_roundtrip_via_sanitize() -> None:
    raw = sanitize_prefs({"reminder_time": "07:15", "reminder_tz": "Asia/Tokyo"})
    assert raw["reminder_time"] == "07:15"
    assert raw["reminder_tz"] == "Asia/Tokyo"


@pytest.mark.asyncio
async def test_run_reminder_cycle_for_user(db_session: AsyncSession, test_user: User) -> None:
    from app.reminders.engine import run_reminder_cycle_for_user

    med = Medication(user_id=test_user.id, name="Vitamin D", kind="supplement")
    db_session.add(med)
    await db_session.flush()
    db_session.add(
        MedSchedule(
            user_id=test_user.id,
            medication_id=med.id,
            dose_quantity=1,
            dose_unit="tab",
            frequency_type="daily",
            times_per_day=2,
            is_active=True,
        )
    )
    await db_session.flush()

    # Per-user schedule: the daily cycle must run in this user's own tz.
    test_user.prefs = sanitize_prefs({"reminder_time": "08:00", "reminder_tz": "Europe/Moscow"})
    db_session.add(test_user)
    await db_session.flush()

    delivered = await run_reminder_cycle_for_user(db_session, test_user, mode="daily")
    await db_session.commit()

    assert delivered >= 1
    notifs = (
        (await db_session.execute(select(Notification).where(Notification.user_id == test_user.id)))
        .scalars()
        .all()
    )
    assert any(n.type == "reminder" for n in notifs)
