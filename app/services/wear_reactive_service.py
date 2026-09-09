"""Wear Reactive Service for Open-Ended Wear mode (ADR-195).

Manages open-ended lifestyle chastity wear, second-accurate state tracking,
reason-based unlock workflows, strict deadline penalty enforcement, and
cross-domain reactive integrations (Sexual Journal, Care, Training, Points).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import JournalEntry
from app.models.locktimer import LockSession, LockSlotOccurrence
from app.models.points import PointsTransaction
from app.models.wear_events import WearEventDefinition, WearEventLog
from app.timeutils import as_utc

logger = logging.getLogger(__name__)


def format_duration_hms(total_seconds: int) -> str:
    """Formats total seconds into 'X дн. Y ч. Z мин. W сек.' with second-level precision."""
    if total_seconds < 0:
        total_seconds = 0
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    parts = []
    if days > 0:
        parts.append(f"{days} дн.")
    if hours > 0 or days > 0:
        parts.append(f"{hours} ч.")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes} мин.")
    parts.append(f"{seconds} сек.")
    return " ".join(parts)


async def get_or_create_open_ended_session(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> LockSession:
    """Retrieves an active open-ended wear session or creates a new one."""
    stmt = (
        select(LockSession)
        .where(
            LockSession.owner_id == user_id,
            LockSession.state == "active",
        )
        .order_by(desc(LockSession.created_at))
    )
    res = await db.execute(stmt)
    session = res.scalars().first()

    now = datetime.now(UTC)
    if not session:
        session = LockSession(
            owner_id=user_id,
            mode="open_ended",
            state="active",
            is_currently_locked=True,
            started_at=now,
            random_seed_encrypted="open_ended",
            random_seed_commitment="open_ended",
            duration_type="open_ended",
            timezone="UTC",
        )
        db.add(session)
        await db.flush()
    else:
        # Upgrade or ensure open_ended mode
        if session.mode != "open_ended":
            session.mode = "open_ended"
            if session.is_currently_locked is None:
                session.is_currently_locked = True
            await db.flush()

    return session


async def get_wear_status(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """Computes real-time status of wear, exact second timer, pending opens, and day slots."""
    session = await get_or_create_open_ended_session(db, user_id)
    now = datetime.now(UTC)

    pending_open: WearEventLog | None = None
    if session.pending_open_event_id:
        pending_open = (
            await db.execute(select(WearEventLog).where(WearEventLog.id == session.pending_open_event_id))
        ).scalars().first()

    # If is_currently_locked is False but pending_open is missing, search last open log
    if not session.is_currently_locked and not pending_open:
        pending_open = (
            await db.execute(
                select(WearEventLog)
                .where(
                    WearEventLog.user_id == user_id,
                    WearEventLog.state_after == "unlocked",
                    WearEventLog.relocked_at.is_(None),
                )
                .order_by(desc(WearEventLog.created_at))
            )
        ).scalars().first()

    time_text = ""
    deadline_text = ""
    is_overdue = False
    duration_sec = 0

    if session.is_currently_locked:
        # Compute wear streak duration from last relock or started_at
        last_relock = as_utc(session.last_wear_checkin_at or session.started_at or now)
        duration_sec = max(0, int((now - last_relock).total_seconds()))
        time_text = f"🔒 Заперт: {format_duration_hms(duration_sec)}"
    else:
        open_time = as_utc((pending_open.opened_at if pending_open else None) or session.updated_at or now)
        duration_sec = max(0, int((now - open_time).total_seconds()))
        time_text = f"🔓 Снят: {format_duration_hms(duration_sec)}"

        if pending_open and pending_open.expected_relock_at:
            exp_time = as_utc(pending_open.expected_relock_at)
            diff_sec = int((exp_time - now).total_seconds())
            if diff_sec >= 0:
                deadline_text = f"⏳ До закрытия: {format_duration_hms(diff_sec)}"
            else:
                is_overdue = True
                overdue_sec = abs(diff_sec)
                deadline_text = f"⚠️ ПРОСРОЧЕНО на {format_duration_hms(overdue_sec)}! Действует штраф!"

    # Find today's scheduled lock slot occurrences
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    slots_res = await db.execute(
        select(LockSlotOccurrence)
        .where(
            LockSlotOccurrence.session_id == session.id,
            LockSlotOccurrence.planned_open_at >= today_start,
            LockSlotOccurrence.planned_open_at < today_end,
        )
        .order_by(LockSlotOccurrence.planned_open_at)
    )
    today_slots = slots_res.scalars().all()

    upcoming_slots: list[dict[str, Any]] = []
    for slot in today_slots:
        upcoming_slots.append({
            "id": slot.id,
            "planned_open_at": slot.planned_open_at,
            "planned_close_at": slot.planned_close_at,
            "state": slot.state,
        })

    return {
        "session": session,
        "is_locked": session.is_currently_locked,
        "current_tag": session.current_tag_number,
        "last_comfort": session.last_comfort_score,
        "time_text": time_text,
        "deadline_text": deadline_text,
        "is_overdue": is_overdue,
        "duration_sec": duration_sec,
        "pending_open": pending_open,
        "upcoming_slots": upcoming_slots,
    }


async def record_unlock_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    event_code: str,
    duration_minutes: int | None = None,
    user_comment: str | None = None,
    llm_analysis: str | None = None,
) -> tuple[WearEventLog, dict[str, Any]]:
    """Records an unlock event, computes return deadline, and triggers reactive side effects."""
    session = await get_or_create_open_ended_session(db, user_id)
    now = datetime.now(UTC)

    def_item = (
        await db.execute(select(WearEventDefinition).where(WearEventDefinition.code == event_code))
    ).scalars().first()

    eff_duration_mins = duration_minutes
    if eff_duration_mins is None and def_item:
        eff_duration_mins = def_item.default_duration_minutes

    expected_relock_at = None
    if eff_duration_mins:
        expected_relock_at = now + timedelta(minutes=eff_duration_mins)

    open_log = WearEventLog(
        user_id=user_id,
        device_id=session.chastity_device_id or session.device_id,
        session_id=session.id,
        event_code=event_code,
        event_def_id=def_item.id if def_item else None,
        state_before="locked",
        state_after="unlocked",
        opened_at=now,
        expected_relock_at=expected_relock_at,
        tag_number=session.current_tag_number,
        user_comment=user_comment,
        llm_analysis=llm_analysis,
        reactions_applied={},
    )
    db.add(open_log)
    await db.flush()

    session.is_currently_locked = False
    session.pending_open_event_id = open_log.id
    session.updated_at = now

    reactions: dict[str, Any] = {}

    # 1. Reactive Trigger: Sex Activity -> record to Sexual Journal (PRODUCT_OVERVIEW §7)
    if event_code == "sex_activity":
        try:
            journal_entry = JournalEntry(
                user_id=user_id,
                entry_date=now.date(),
                activity_type="Секс (снятие пояса)",
                duration_minutes=eff_duration_mins or 60,
                status="draft",
                source="timer_slot",
                timer_session_id=session.id,
                notes=f"Автоматически создано при снятии пояса. Причина: {user_comment or 'Секс'}",
            )
            db.add(journal_entry)
            await db.flush()
            reactions["sexual_journal_id"] = str(journal_entry.id)
            reactions["sexual_journal_message"] = "Создана черновая запись в Сексуальном журнале."
        except Exception as e:
            logger.exception("Failed to create JournalEntry for sex_activity: %s", e)

    # 2. Reactive Trigger: Breach / Relapse -> Immediate Penalty
    elif event_code == "breach_relapse":
        penalty_amount = -50
        penalty_tx = PointsTransaction(
            user_id=user_id,
            amount=penalty_amount,
            transaction_type="penalty",
            reason=f"Штраф за срыв / несанкционированное снятие пояса: {user_comment or 'Срыв'}",
        )
        db.add(penalty_tx)
        reactions["penalty_applied"] = penalty_amount
        reactions["penalty_message"] = f"Начислен штраф {penalty_amount} баллов за срыв."

    # 3. Reactive Trigger: Care Grooming -> Note care activity
    elif event_code == "care_grooming":
        reactions["care_triggered"] = True
        reactions["care_message"] = "Зафиксирован уход и гигиенические процедуры."

    # 4. Reactive Trigger: Sport Workout
    elif event_code == "sport_workout":
        reactions["sport_triggered"] = True
        reactions["sport_message"] = "Интенсивная тренировка зафиксирована."

    open_log.reactions_applied = reactions
    await db.commit()
    await db.refresh(open_log)
    return open_log, reactions


async def record_relock_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    tag_number: str | None = None,
    comfort_score: int | None = None,
    user_comment: str | None = None,
) -> tuple[WearEventLog, dict[str, Any]]:
    """Records relock event, calculates exact overtime penalty, and restores locked state."""
    session = await get_or_create_open_ended_session(db, user_id)
    now = datetime.now(UTC)

    open_log: WearEventLog | None = None
    if session.pending_open_event_id:
        open_log = (
            await db.execute(select(WearEventLog).where(WearEventLog.id == session.pending_open_event_id))
        ).scalars().first()

    reactions: dict[str, Any] = {}
    duration_sec = None

    if open_log:
        open_log.relocked_at = now
        opened_at = as_utc(open_log.opened_at) if open_log.opened_at else None
        duration_sec = max(0, int((now - opened_at).total_seconds())) if opened_at else 0
        open_log.duration_seconds = duration_sec
        open_log.tag_number = tag_number or open_log.tag_number
        open_log.comfort_score = comfort_score or open_log.comfort_score

        # Strict Penalty Check: Any second past expected_relock_at is penalized!
        if open_log.expected_relock_at:
            exp_time = as_utc(open_log.expected_relock_at)
            if now > exp_time:
                overdue_sec = int((now - exp_time).total_seconds())
                if overdue_sec > 0:
                    base_penalty = 10
                    minute_penalty = (overdue_sec // 60) * 2
                    total_penalty = -(base_penalty + minute_penalty)

                    penalty_tx = PointsTransaction(
                        user_id=user_id,
                        amount=total_penalty,
                        transaction_type="penalty",
                        reason=f"Штраф за опоздание с возвратом пояса на {format_duration_hms(overdue_sec)}",
                    )
                    db.add(penalty_tx)
                    reactions["delay_penalty"] = {
                        "overdue_seconds": overdue_sec,
                        "amount": total_penalty,
                        "formatted_overdue": format_duration_hms(overdue_sec),
                    }

    relock_log = WearEventLog(
        user_id=user_id,
        device_id=session.chastity_device_id or session.device_id,
        session_id=session.id,
        event_code="relock",
        state_before="unlocked",
        state_after="locked",
        relocked_at=now,
        duration_seconds=duration_sec,
        comfort_score=comfort_score,
        tag_number=tag_number,
        user_comment=user_comment,
        reactions_applied=reactions,
    )
    db.add(relock_log)

    session.is_currently_locked = True
    session.pending_open_event_id = None
    if tag_number:
        session.current_tag_number = tag_number
    if comfort_score:
        session.last_comfort_score = comfort_score
    session.last_wear_checkin_at = now
    session.updated_at = now

    await db.commit()
    await db.refresh(relock_log)
    return relock_log, reactions


async def record_seal_inspection(
    db: AsyncSession,
    user_id: uuid.UUID,
    tag_number: str,
    comfort_score: int | None = None,
    notes: str | None = None,
) -> WearEventLog:
    """Records a seal / tag inspection without unlocking the device (inspection-only)."""
    session = await get_or_create_open_ended_session(db, user_id)
    now = datetime.now(UTC)

    inspection_log = WearEventLog(
        user_id=user_id,
        device_id=session.chastity_device_id or session.device_id,
        session_id=session.id,
        event_code="seal_inspection",
        state_before="locked",
        state_after="locked",
        tag_number=tag_number,
        comfort_score=comfort_score,
        user_comment=notes,
        reactions_applied={"inspection_verified": True},
    )
    db.add(inspection_log)

    session.current_tag_number = tag_number
    if comfort_score:
        session.last_comfort_score = comfort_score
    session.last_wear_checkin_at = now
    session.updated_at = now

    await db.commit()
    await db.refresh(inspection_log)
    return inspection_log


async def record_orgasm_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    orgasms_count: int = 1,
    notes: str | None = None,
) -> tuple[WearEventLog, dict[str, Any]]:
    """Records orgasm/release event into wear log and Sexual Journal."""
    session = await get_or_create_open_ended_session(db, user_id)
    now = datetime.now(UTC)

    cur_state = "locked" if session.is_currently_locked else "unlocked"
    reactions: dict[str, Any] = {}

    try:
        journal_entry = JournalEntry(
            user_id=user_id,
            entry_date=now.date(),
            activity_type="Оргазм / Эякуляция",
            orgasms=orgasms_count,
            status="completed",
            source="timer_slot",
            timer_session_id=session.id,
            notes=notes or "Фиксация оргазма через таймер ношения",
        )
        db.add(journal_entry)
        await db.flush()
        reactions["sexual_journal_id"] = str(journal_entry.id)
        reactions["message"] = f"Зафиксировано оргазмов: {orgasms_count} в Сексуальном журнале."
    except Exception as e:
        logger.exception("Failed to record orgasm in JournalEntry: %s", e)

    orgasm_log = WearEventLog(
        user_id=user_id,
        device_id=session.chastity_device_id or session.device_id,
        session_id=session.id,
        event_code="orgasm_release",
        state_before=cur_state,
        state_after=cur_state,
        user_comment=notes,
        reactions_applied=reactions,
    )
    db.add(orgasm_log)
    await db.commit()
    await db.refresh(orgasm_log)
    return orgasm_log, reactions
