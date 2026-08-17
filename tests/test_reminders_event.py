"""Event reminders (ADR-096) — "shortly before" notifications.

Covers the event-mode collectors added on top of the daily batch:
- ``_medication_dose_reminders`` — a dose at a specific ``times_of_day`` time
  fires only within the lead window (and dedupes per dose time/day);
- ``_timer_reminders`` — a timer window opening / task due within the lead
  window fires once per occurrence;
- ``run_reminder_cycle(mode="event")`` — delivers event reminders to all users.

Relief-only (PD-013): these reminders never apply points/penalties.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.locktimer import domain as d
from app.locktimer import enums as e
from app.models.locktimer import LockSession, LockSlotOccurrence, LockSlotRule
from app.models.medication import Medication, MedSchedule
from app.models.reminder_log import ReminderLog


async def _add_med_schedule(db_session, user, times_of_day):
    med = Medication(user_id=user.id, name="Ibuprofen", kind="medication")
    db_session.add(med)
    await db_session.flush()
    sched = MedSchedule(
        user_id=user.id,
        medication_id=med.id,
        dose_quantity=1,
        frequency_type="daily",
        times_of_day=times_of_day,
        is_active=True,
    )
    db_session.add(sched)
    await db_session.flush()
    return sched


async def _add_active_session_with_slot(db_session, user, planned_open_at: datetime) -> LockSlotOccurrence:
    seed = d.generate_random_seed()
    session = LockSession(
        id=uuid.uuid4(),
        owner_id=user.id,
        state=e.SESSION_ACTIVE,
        duration_type=e.DURATION_FROM_START,
        timezone="UTC",
        merge_gap_seconds=3600,
        random_seed_encrypted=seed,
        random_seed_commitment=d.compute_seed_commitment(seed),
        privacy_mode="private",
        row_version=1,
    )
    db_session.add(session)
    await db_session.flush()
    rule = LockSlotRule(
        id=uuid.uuid4(),
        session_id=session.id,
        name="window",
        rule_type=e.SLOT_RULE_EXACT_DATETIME,
        schedule={},
        duration_seconds=3600,
        schema_version=1,
    )
    db_session.add(rule)
    await db_session.flush()
    occ = LockSlotOccurrence(
        id=uuid.uuid4(),
        session_id=session.id,
        rule_id=rule.id,
        occurrence_key="k1",
        planned_open_at=planned_open_at,
        eligible_from=planned_open_at - timedelta(hours=1),
        eligible_until=planned_open_at + timedelta(hours=1),
        state="pending",
    )
    db_session.add(occ)
    await db_session.flush()
    return occ


@pytest.mark.asyncio
async def test_med_dose_fires_only_within_lead_window(db_session, test_user):
    from app.reminders.engine import collect_reminders

    await _add_med_schedule(db_session, test_user, ["08:00"])

    # 20 minutes before the dose → within the 30m lead window.
    now_soon = datetime.now(UTC).replace(hour=7, minute=40, second=0, microsecond=0)
    reminders = await collect_reminders(db_session, test_user.id, now_soon.date(), now_soon, mode="event")
    assert any(r.kind == "med_dose" for r in reminders)

    # 60 minutes before → outside the lead window.
    now_early = datetime.now(UTC).replace(hour=7, minute=0, second=0, microsecond=0)
    reminders = await collect_reminders(db_session, test_user.id, now_early.date(), now_early, mode="event")
    assert not any(r.kind == "med_dose" for r in reminders)


@pytest.mark.asyncio
async def test_med_dose_dedupes_per_dose_time(db_session, test_user):
    from app.reminders.engine import collect_reminders, deliver_reminders

    sched = await _add_med_schedule(db_session, test_user, ["08:00"])
    now = datetime.now(UTC).replace(hour=7, minute=45, second=0, microsecond=0)
    reminders = await collect_reminders(db_session, test_user.id, now.date(), now, mode="event")
    delivered = await deliver_reminders(db_session, test_user, reminders)
    assert delivered == 1

    # Same window again → deduped.
    delivered2 = await deliver_reminders(db_session, test_user, reminders)
    assert delivered2 == 0
    key = f"med_dose:{sched.id}:{now.date().isoformat()}:08:00"
    row = (
        await db_session.execute(
            select(ReminderLog).where(ReminderLog.user_id == test_user.id, ReminderLog.dedupe_key == key)
        )
    ).scalar_one_or_none()
    assert row is not None


@pytest.mark.asyncio
async def test_timer_slot_fires_within_lead_window(db_session, test_user):
    from app.reminders.engine import collect_reminders

    now = datetime.now(UTC)
    await _add_active_session_with_slot(db_session, test_user, now + timedelta(minutes=20))

    reminders = await collect_reminders(db_session, test_user.id, now.date(), now, mode="event")
    assert any(r.kind == "timer_slot_upcoming" for r in reminders)


@pytest.mark.asyncio
async def test_timer_slot_outside_lead_is_silent(db_session, test_user):
    from app.reminders.engine import collect_reminders

    now = datetime.now(UTC)
    # 2 hours ahead → outside the lead window.
    await _add_active_session_with_slot(db_session, test_user, now + timedelta(hours=2))

    reminders = await collect_reminders(db_session, test_user.id, now.date(), now, mode="event")
    assert not any(r.kind == "timer_slot_upcoming" for r in reminders)


@pytest.mark.asyncio
async def test_run_reminder_cycle_event_mode(db_session, test_user):
    from app.reminders.engine import run_reminder_cycle

    now = datetime.now(UTC)
    await _add_med_schedule(db_session, test_user, [f"{now:%H}:{(now.minute + 5) % 60:02d}"])
    await _add_active_session_with_slot(db_session, test_user, now + timedelta(minutes=20))

    total = await run_reminder_cycle(db_session, tz_name="UTC", mode="event")
    assert total >= 1


@pytest.mark.asyncio
async def test_config_event_defaults_present():
    from app.config import settings

    assert settings.reminder_event_interval_minutes >= 1
    assert settings.reminder_event_lead_minutes >= 1
