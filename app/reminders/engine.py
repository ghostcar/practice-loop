"""Reminder engine — collect due reminders and deliver them.

The engine is **stateless per cycle**: ``collect_reminders`` gathers the due
reminders for one user; ``deliver_reminders`` writes them to the in-app
Notification table and dispatches Telegram + push, deduplicating via
``reminder_log`` so the same item isn't re-notified every cycle.

Relief-only (PD-013): reminders never apply points/penalties. Telegram/push
text is neutralized under discretion (ADR-081, ``neutral_notification``).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.prefs import neutral_notification, prefs_from_dict
from app.timeutils import resolve_tz

if TYPE_CHECKING:
    from app.models.user import User

logger = logging.getLogger(__name__)

# Care product low-stock threshold (quantity <= 1) mirrors the /care badge.
CARE_LOW_STOCK = 1
CARE_EXPIRING_DAYS = 30


def _lead_minutes() -> int:
    """How far ahead of an event the "shortly before" reminders fire (ADR-096)."""
    return max(1, settings.reminder_event_lead_minutes)


@dataclass
class Reminder:
    kind: str
    title: str
    body: str | None
    link: str
    dedupe_key: str


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------


async def _medication_reminders(db: AsyncSession, user_id: uuid.UUID, today: date) -> list[Reminder]:
    from app.models.medication import MedIntake, MedSchedule, MedStock

    out: list[Reminder] = []
    schedules = (
        (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user_id, MedSchedule.is_active.is_(True))))
        .scalars()
        .all()
    )
    intakes = (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id))).scalars().all()

    taken_today: dict[str, int] = {}
    for it in intakes:
        if it.status != "taken" or it.schedule_id is None:
            continue
        taken_dt = it.taken_at or it.created_at
        if taken_dt is not None and taken_dt.astimezone(resolve_tz("UTC")).date() == today:
            taken_today[str(it.schedule_id)] = taken_today.get(str(it.schedule_id), 0) + 1

    for s in schedules:
        # Ожидаемое число приёмов сегодня (дублируем _doses_today — без импорта api-слоя).
        if s.start_date and today < s.start_date:
            continue
        if s.end_date and today > s.end_date:
            continue
        if s.frequency_type == "weekly":
            if s.days_of_week and today.weekday() not in s.days_of_week:
                continue
            expected = s.times_per_day or 1
        elif s.frequency_type == "interval":
            if not s.interval_hours:
                continue
            expected = max(1, int(24 // s.interval_hours))
        else:
            expected = s.times_per_day or len(s.times_of_day or []) or 1
        if expected <= 0:
            continue
        done = taken_today.get(str(s.id), 0)
        pending = max(0, expected - done)
        if pending > 0:
            name = s.medication.name if s.medication else "?"
            dose = f"{s.dose_quantity:g} {s.dose_unit or ''}".strip()
            out.append(
                Reminder(
                    kind="med_due",
                    title=f"Medication due: {name}",
                    body=f"Take {dose} — {pending} dose(s) pending today.",
                    link="/medications",
                    dedupe_key=f"med_due:{s.id}:{today.isoformat()}",
                )
            )

    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user_id))).scalars().all()
    for st in stocks:
        name = st.medication.name if st.medication else "?"
        if st.expiry_date is not None and (st.expiry_date - today).days <= 30:
            out.append(
                Reminder(
                    kind="med_expiring",
                    title=f"Expiring: {name}",
                    body=f"Expires {st.expiry_date.isoformat()}.",
                    link="/medications",
                    dedupe_key=f"med_expiring:{st.id}",
                )
            )
        if st.low_stock_threshold is not None and st.quantity <= st.low_stock_threshold:
            out.append(
                Reminder(
                    kind="med_low",
                    title=f"Low stock: {name}",
                    body=f"Quantity {st.quantity:g} (threshold {st.low_stock_threshold:g}).",
                    link="/medications",
                    dedupe_key=f"med_low:{st.id}",
                )
            )
    return out


async def _care_product_reminders(db: AsyncSession, user_id: uuid.UUID, today: date) -> list[Reminder]:
    from app.models.care import CareProduct

    out: list[Reminder] = []
    products = (await db.execute(select(CareProduct).where(CareProduct.user_id == user_id))).scalars().all()
    for p in products:
        if p.quantity is not None and 0 < p.quantity <= CARE_LOW_STOCK:
            out.append(
                Reminder(
                    kind="care_product_low",
                    title=f"Low stock: {p.name}",
                    body="Running low — consider restocking.",
                    link="/care",
                    dedupe_key=f"care_product_low:{p.id}",
                )
            )
        if p.expiry_date is not None and (p.expiry_date - today).days <= CARE_EXPIRING_DAYS:
            out.append(
                Reminder(
                    kind="care_product_expiring",
                    title=f"Expiring: {p.name}",
                    body=f"Expires {p.expiry_date.isoformat()}.",
                    link="/care",
                    dedupe_key=f"care_product_expiring:{p.id}",
                )
            )
    return out


async def _care_routine_reminders(db: AsyncSession, user_id: uuid.UUID, today: date) -> list[Reminder]:
    from app.models.care import CareEntry, CareRoutine

    out: list[Reminder] = []
    routines = (await db.execute(select(CareRoutine).where(CareRoutine.user_id == user_id))).scalars().all()
    entries = (await db.execute(select(CareEntry).where(CareEntry.user_id == user_id))).scalars().all()
    last_entry: dict[str, date] = {}
    for e in entries:
        if e.routine_id is None:
            continue
        key = str(e.routine_id)
        if key not in last_entry or e.entry_date > last_entry[key]:
            last_entry[key] = e.entry_date
    for r in routines:
        if not r.frequency_days:
            continue
        prev = last_entry.get(str(r.id))
        if prev is not None and (today - prev).days < r.frequency_days:
            continue
        out.append(
            Reminder(
                kind="care_routine_due",
                title=f"Care routine due: {r.name}",
                body=f"Due every {r.frequency_days} days.",
                link="/care",
                dedupe_key=f"care_routine_due:{r.id}:{today.isoformat()}",
            )
        )
    return out


async def _care_course_reminders(db: AsyncSession, user_id: uuid.UUID, today: date) -> list[Reminder]:
    from app.models.care import CareCourse

    out: list[Reminder] = []
    courses = (
        (await db.execute(select(CareCourse).where(CareCourse.user_id == user_id, CareCourse.status == "active")))
        .scalars()
        .all()
    )
    for c in courses:
        pending = sorted((s for s in c.sessions if s.status == "pending"), key=lambda s: s.scheduled_date)
        if not pending:
            continue
        nxt = pending[0]
        if nxt.scheduled_date <= today + timedelta(days=2):
            out.append(
                Reminder(
                    kind="care_course_session",
                    title=f"Course session: {c.name}",
                    body=f"Session {nxt.session_number}/{c.total_sessions} on {nxt.scheduled_date.isoformat()}.",
                    link="/care",
                    dedupe_key=f"care_course_session:{nxt.id}",
                )
            )
    return out


async def _medication_dose_reminders(db: AsyncSession, user_id: uuid.UUID, now) -> list[Reminder]:
    """Event: a medication dose at a specific ``times_of_day`` time is coming up.

    Fires within ``[dose_time - lead, dose_time]`` so the user gets a nudge
    shortly before the dose is due (not just in the morning batch). The
    ``reminder_log`` dedupe (per dose time/day) already guarantees a single
    notification, and the window naturally closes once the dose time passes.
    """
    from app.models.medication import MedSchedule

    lead = timedelta(minutes=_lead_minutes())
    window_end = now + lead
    out: list[Reminder] = []
    schedules = (
        (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user_id, MedSchedule.is_active.is_(True))))
        .scalars()
        .all()
    )

    for s in schedules:
        if not s.times_of_day:
            continue
        if s.start_date and now.date() < s.start_date:
            continue
        if s.end_date and now.date() > s.end_date:
            continue
        for t_str in s.times_of_day:
            dose_dt = _parse_hhmm(now, t_str)
            if dose_dt is None:
                continue
            if not (now <= dose_dt <= window_end):
                continue
            name = s.medication.name if s.medication else "?"
            dose = f"{s.dose_quantity:g} {s.dose_unit or ''}".strip()
            out.append(
                Reminder(
                    kind="med_dose",
                    title=f"Medication soon: {name}",
                    body=f"Take {dose} at {t_str}.",
                    link="/medications",
                    dedupe_key=f"med_dose:{s.id}:{now.date().isoformat()}:{t_str}",
                )
            )
    return out


def _parse_hhmm(now, t_str: str):
    """Parse ``HH:MM`` into an aware datetime on ``now``'s day (None on bad input)."""
    try:
        hour = int(t_str[:2])
        minute = int(t_str[3:5])
    except (ValueError, IndexError):
        return None
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


async def _timer_reminders(db: AsyncSession, user_id: uuid.UUID, now) -> list[Reminder]:
    """Event: a timer window opens / task is due within the lead window (ADR-096)."""
    from app.locktimer import enums as e
    from app.models.locktimer import LockSession, LockSlotOccurrence, LockTaskOccurrence

    lead = timedelta(minutes=_lead_minutes())
    window_end = now + lead
    out: list[Reminder] = []
    sessions = (
        (
            await db.execute(
                select(LockSession).where(LockSession.owner_id == user_id, LockSession.state == e.SESSION_ACTIVE)
            )
        )
        .scalars()
        .all()
    )
    for session in sessions:
        slots = (
            (
                await db.execute(
                    select(LockSlotOccurrence).where(
                        LockSlotOccurrence.session_id == session.id,
                        LockSlotOccurrence.state.in_(["pending", "eligible"]),
                        LockSlotOccurrence.planned_open_at >= now,
                        LockSlotOccurrence.planned_open_at <= window_end,
                    )
                )
            )
            .scalars()
            .all()
        )
        for occ in slots:
            out.append(
                Reminder(
                    kind="timer_slot_upcoming",
                    title="Timer window opening soon",
                    body=f"Window at {occ.planned_open_at.isoformat(timespec='minutes')}.",
                    link=f"/locktimer/sessions/{session.id}",
                    dedupe_key=f"timer_slot_upcoming:{occ.id}",
                )
            )
        tasks = (
            (
                await db.execute(
                    select(LockTaskOccurrence).where(
                        LockTaskOccurrence.session_id == session.id,
                        LockTaskOccurrence.state.in_(["scheduled", "visible"]),
                        LockTaskOccurrence.due_at >= now,
                        LockTaskOccurrence.due_at <= window_end,
                    )
                )
            )
            .scalars()
            .all()
        )
        for occ in tasks:
            out.append(
                Reminder(
                    kind="timer_task_due",
                    title="Timer task due",
                    body=f"Task due at {occ.due_at.isoformat(timespec='minutes')}.",
                    link=f"/locktimer/sessions/{session.id}",
                    dedupe_key=f"timer_task_due:{occ.id}",
                )
            )
    return out


async def collect_reminders(
    db: AsyncSession, user_id: uuid.UUID, today: date, now, mode: str = "daily"
) -> list[Reminder]:
    """Gather due reminders for one user (best-effort per module).

    ``mode="daily"`` — the morning batch (medication due summary, low stock /
    expiry, care routine/course heads-up). ``mode="event"`` — "shortly before"
    reminders (timer window/task, medication dose at a specific time, ADR-096).
    """
    out: list[Reminder] = []
    if mode == "event":
        collectors = (_medication_dose_reminders, _timer_reminders)
        for collector in collectors:
            try:
                out.extend(await collector(db, user_id, now))
            except Exception:
                logger.warning(
                    "reminder collector %s failed for %s",
                    getattr(collector, "__name__", "?"),
                    user_id,
                    exc_info=True,
                )
        return out

    date_collectors = (
        _medication_reminders,
        _care_product_reminders,
        _care_routine_reminders,
        _care_course_reminders,
    )
    for collector in date_collectors:
        try:
            out.extend(await collector(db, user_id, today))
        except Exception:
            logger.warning(
                "reminder collector %s failed for %s",
                getattr(collector, "__name__", "?"),
                user_id,
                exc_info=True,
            )
    return out


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


async def deliver_reminders(db: AsyncSession, user: User, reminders: list[Reminder]) -> int:
    """Persist + dispatch due reminders, deduping against reminder_log.

    Returns the number of newly delivered reminders.
    """
    if not reminders:
        return 0

    from app.models.notification import Notification
    from app.models.reminder_log import ReminderLog

    existing = (
        (
            await db.execute(
                select(ReminderLog.dedupe_key).where(
                    ReminderLog.user_id == user.id,
                    ReminderLog.kind.in_({r.kind for r in reminders}),
                )
            )
        )
        .scalars()
        .all()
    )
    seen = set(existing)
    prefs = prefs_from_dict(user.prefs) if hasattr(user, "prefs") else None

    delivered = 0
    fresh: list[Reminder] = []
    for r in reminders:
        if r.dedupe_key in seen:
            continue
        seen.add(r.dedupe_key)
        fresh.append(r)

    if not fresh:
        return 0

    for r in fresh:
        title, body = neutral_notification(prefs, r.title, r.body, getattr(user, "locale", "en") or "en")
        db.add(ReminderLog(user_id=user.id, kind=r.kind, dedupe_key=r.dedupe_key))
        db.add(Notification(user_id=user.id, type="reminder", title=title, body=body, link=r.link))
        delivered += 1

    await db.flush()

    # Telegram + push (best-effort, never raises).
    if user.telegram_chat_id:
        from app.telegram.bot import send_telegram_notification

        for r in fresh[:5]:
            title, body = neutral_notification(prefs, r.title, r.body, getattr(user, "locale", "en") or "en")
            try:
                await send_telegram_notification(user.telegram_chat_id, f"*{title}*\n{body or ''}")
            except Exception:
                logger.debug("reminder TG send failed", exc_info=True)

    from app.push import dispatch_push

    for r in fresh[:5]:
        title, body = neutral_notification(prefs, r.title, r.body, getattr(user, "locale", "en") or "en")
        try:
            await dispatch_push(db, user.id, title, body, data={"type": "reminder", "link": r.link})
        except Exception:
            logger.debug("reminder push failed", exc_info=True)

    return delivered


async def run_reminder_cycle_for_user(db: AsyncSession, user: User, mode: str = "daily", tz_name: str = "UTC") -> int:
    """Run one reminder cycle for a single user in their own timezone (ADR-098).

    "Today"/"now" are computed in the user's ``prefs.reminder_tz`` (falling back
    to ``tz_name``, i.e. the global ``settings.reminder_tz``), so medication dose
    times and day boundaries match the user's local day.
    """
    prefs = prefs_from_dict(user.prefs) if hasattr(user, "prefs") else None
    tz = resolve_tz((prefs.reminder_tz if prefs else None) or tz_name)
    now = _now(tz)
    today = now.date()
    reminders = await collect_reminders(db, user.id, today, now, mode=mode)
    return await deliver_reminders(db, user, reminders)


async def run_reminder_cycle(db: AsyncSession, tz_name: str = "UTC", mode: str = "daily") -> int:
    """Run one reminder cycle for all users (per-user timezone, ADR-098).

    ``tz_name`` is the fallback for users who haven't configured their own
    ``prefs.reminder_tz``. Returns total delivered count.
    """
    from app.models.user import User

    users = (await db.execute(select(User))).scalars().all()
    total = 0
    for user in users:
        try:
            total += await run_reminder_cycle_for_user(db, user, mode=mode, tz_name=tz_name)
        except Exception:
            logger.warning("reminder cycle failed for %s", user.id, exc_info=True)
    await db.commit()
    return total


def _now(tz) -> datetime:
    return datetime.now(tz)
