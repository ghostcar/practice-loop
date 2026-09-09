"""Gamification Extensions & Mini-Games for LockSessions (ADR-198).

Chaster.app-inspired mechanisms:
1. Wheel of Fortune (time additions, mercy reductions, freezes, pillory, challenge, XP).
2. Dice of Fate (2d6 rolls with critical fail, bad luck, test, mercy, jackpot).
3. Humiliation & Obedience Photo Challenges with one-time verification codes and deadlines.
4. Temporal Anomaly / Time Jump by AI Keyholder.
5. Persistent history of all games in lock_game_actions.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer.repositories import get_session
from app.locktimer.services.discipline_service import (
    create_session_verification_challenge,
    send_session_to_pillory,
    verify_session_photo_submission,
)
from app.models.locktimer import LockGameAction, LockSession
from app.models.user import User
from app.services import identity_service
from app.timeutils import as_utc

logger = logging.getLogger(__name__)

# Catalog of Obedience & Humiliation Challenges
OBEDIENCE_CHALLENGES = {
    "kneeling_repentance": {
        "type": "kneeling_repentance",
        "title": "Покаяние на коленях",
        "badge": "Колени и замок",
        "description": (
            "Встать на колени перед зеркалом или камерой в надетом поясе. "
            "Написать на бумаге разовый проверочный код и номер пломбы. "
            "Сделать четкое фото, на котором видны поза покорности, замок и табличка."
        ),
        "duration_minutes": 45,
        "reward_seconds": -1800,  # -30 min
        "reward_xp": 50,
        "penalty_seconds": 7200,  # +2 hours
        "penalty_xp": -50,
        "pillory_on_fail": True,
    },
    "body_marking": {
        "type": "body_marking",
        "title": "Клеймо позора на теле",
        "badge": "Маркировка тела",
        "description": (
            "Косметическим маркером или помадой написать на коже бедра рядом с замком "
            "текущую дату, статус 'PROPERTY' и проверочный код. Сделать четкое фото крупным планом с замком."
        ),
        "duration_minutes": 45,
        "reward_seconds": -2700,  # -45 min
        "reward_xp": 70,
        "penalty_seconds": 10800,  # +3 hours
        "penalty_xp": -70,
        "pillory_on_fail": True,
    },
    "sissy_pet_gear": {
        "type": "sissy_pet_gear",
        "title": "Унизительный наряд / Питомец",
        "badge": "Атрибут питомца",
        "description": (
            "Надеть ошейник с поводком, ушки питомца или сисси-чулки вместе с поясом верности. "
            "Написать табличку с проверочным кодом. Сделать фото в полный рост или у зеркала."
        ),
        "duration_minutes": 60,
        "reward_seconds": -3600,  # -1 hour
        "reward_xp": 100,
        "penalty_seconds": 14400,  # +4 hours
        "penalty_xp": -100,
        "pillory_on_fail": True,
    },
    "deep_kowtow": {
        "type": "deep_kowtow",
        "title": "Полный поклон подчинения (Котоу)",
        "badge": "Глубокий поклон",
        "description": (
            "Поза полного поклона (лоб и ладони на полу, пояс виден со спины, "
            "рядом листок с кодом проверки). Сделать фото со спины."
        ),
        "duration_minutes": 45,
        "reward_seconds": -1800,  # -30 min
        "reward_xp": 40,
        "penalty_seconds": 7200,  # +2 hours
        "penalty_xp": -40,
        "pillory_on_fail": False,
    },
    "teeth_sign_inspection": {
        "type": "teeth_sign_inspection",
        "title": "Инспекция с табличкой в зубах",
        "badge": "Табличка в зубах",
        "description": (
            "Табличка с кодом зажата в зубах, обе руки сцеплены за спиной. "
            "Сделать селфи/фото у зеркала с четким фокусом на бирке замка."
        ),
        "duration_minutes": 45,
        "reward_seconds": -2700,  # -45 min
        "reward_xp": 60,
        "penalty_seconds": 9000,  # +2.5 hours
        "penalty_xp": -60,
        "pillory_on_fail": True,
    },
    "public_confession": {
        "type": "public_confession",
        "title": "Публичное раскаяние на Позорном столбе",
        "badge": "Публичное покаяние",
        "description": (
            "Написать краткий текст раскаяния о покорности Ключнику с указанием номера бирки, "
            "прикрепить фото с кодом и опубликовать на Позорный столб."
        ),
        "duration_minutes": 60,
        "reward_seconds": -2700,  # -45 min
        "reward_xp": 80,
        "penalty_seconds": 7200,  # +2 hours
        "penalty_xp": -50,
        "pillory_on_fail": True,
    },
}

# Wheel of fortune sectors and weights
WHEEL_SECTORS = [
    {"code": "+30m", "label": "+30 минут", "time_sec": 1800, "xp": 0, "weight": 20, "type": "time_add"},
    {"code": "+1h", "label": "+1 час", "time_sec": 3600, "xp": 0, "weight": 18, "type": "time_add"},
    {"code": "+3h", "label": "+3 часа", "time_sec": 10800, "xp": 0, "weight": 12, "type": "time_add"},
    {"code": "+6h", "label": "+6 часов", "time_sec": 21600, "xp": 0, "weight": 8, "type": "time_add"},
    {"code": "+12h", "label": "+12 часов", "time_sec": 43200, "xp": 0, "weight": 5, "type": "time_add"},
    {"code": "-15m", "label": "🟢 -15 мин (милость)", "time_sec": -900, "xp": 15, "weight": 10, "type": "time_sub"},
    {"code": "-30m", "label": "🟢 -30 мин (милость)", "time_sec": -1800, "xp": 30, "weight": 7, "type": "time_sub"},
    {"code": "freeze_2h", "label": "❄️ Заморозка на 2 часа", "time_sec": 7200, "xp": 0, "weight": 6, "type": "freeze"},
    {
        "code": "freeze_perm",
        "label": "❄️ Перманентная заморозка таймера!",
        "time_sec": 0,
        "xp": -20,
        "weight": 4,
        "type": "freeze_perm",
    },
    {
        "code": "unfreeze",
        "label": "🔥 Разморозка таймера!",
        "time_sec": 0,
        "xp": 50,
        "weight": 6,
        "type": "unfreeze",
    },
    {"code": "pillory_2h", "label": "⛓️ Столб на 2 часа", "time_sec": 7200, "xp": -50, "weight": 5, "type": "pillory"},
    {"code": "challenge", "label": "🎭 Испытание", "time_sec": 0, "xp": 0, "weight": 8, "type": "challenge"},
    {"code": "jackpot_xp", "label": "💎 Джекпот (+150 XP)", "time_sec": 0, "xp": 150, "weight": 6, "type": "xp_bonus"},
    {"code": "penalty_xp", "label": "⚠️ Штраф (-100 XP)", "time_sec": 0, "xp": -100, "weight": 5, "type": "xp_penalty"},
]


def _apply_time_modifier_to_session(session: LockSession, delta_seconds: int) -> tuple[datetime, int]:
    """Safely adjusts session.effective_end_at by delta_seconds."""
    now = datetime.now(UTC)
    current_end = as_utc(session.effective_end_at) if session.effective_end_at else now + timedelta(hours=24)

    new_end = current_end + timedelta(seconds=delta_seconds)
    # Ensure end does not fall before now + 5 min if subtracting
    if new_end < now + timedelta(minutes=5):
        new_end = now + timedelta(minutes=5)

    # Respect max_end_at if set
    if session.max_end_at:
        max_end = as_utc(session.max_end_at)
        if new_end > max_end:
            new_end = max_end

    applied_sec = int((new_end - current_end).total_seconds())
    session.effective_end_at = new_end
    return new_end, applied_sec


async def spin_wheel_of_fortune(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    force: bool = False,
) -> dict:
    """Spins the Wheel of Fortune for the active lock session."""
    now = datetime.now(UTC)
    session = await get_session(db, session_id, user_id)
    if session is None or session.state != "active":
        return {"success": False, "error": "Активная сессия не найдена"}

    state = dict(session.extensions_state or {})
    last_spin_str = state.get("last_wheel_spin_at")
    cooldown_hours = state.get("wheel_cooldown_hours", 2)

    if not force and last_spin_str:
        try:
            last_spin = datetime.fromisoformat(last_spin_str)
            if last_spin.tzinfo is None:
                last_spin = last_spin.replace(tzinfo=UTC)
            cooldown_end = last_spin + timedelta(hours=cooldown_hours)
            if now < cooldown_end:
                rem_mins = int((cooldown_end - now).total_seconds() // 60)
                return {
                    "success": False,
                    "error": f"Колесо перезаряжается. До следующего вращения осталось {rem_mins} мин.",
                    "cooldown_remaining_minutes": rem_mins,
                }
        except Exception:
            pass

    # Pick sector by weights
    weights = [s["weight"] for s in WHEEL_SECTORS]
    chosen = random.choices(WHEEL_SECTORS, weights=weights, k=1)[0]

    time_applied_sec = 0
    if chosen["time_sec"] != 0:
        _, time_applied_sec = _apply_time_modifier_to_session(session, chosen["time_sec"])

    # Handle special sector actions
    pillory_triggered = False
    challenge_triggered = False

    if chosen["type"] == "pillory":
        pillory_triggered = True
        await send_session_to_pillory(
            db,
            session,
            reason="Колесо Фортуны: сектор 'Позорный столб'",
            details="Судьба распорядилась отправить вас на суд сообщества на 2 часа.",
        )

    freeze_triggered = False
    unfreeze_triggered = False
    if chosen["type"] == "freeze_perm":
        freeze_triggered = True
        await freeze_session_timer(db, session.id, user_id, reason="Колесо Фортуны: сектор Заморозка")

    if chosen["type"] == "unfreeze":
        unfreeze_triggered = True
        if session.is_frozen:
            await unfreeze_session_timer(db, session.id, user_id, reason="Колесо Фортуны: сектор Разморозка")

    challenge_info = None
    if chosen["type"] == "challenge":
        challenge_triggered = True
        challenge_res = await start_obedience_challenge(db, session_id, user_id)
        if challenge_res.get("success"):
            challenge_info = challenge_res

    # Bad luck streak tracking and status escalation (ADR-200)
    is_bad = chosen["type"] in ("time_add", "pillory", "xp_penalty", "freeze_perm")
    is_jackpot = chosen["type"] in ("jackpot_xp",)

    user = await db.get(User, user_id)
    current_streak = state.get("bad_luck_streak", 0)
    newly_awarded: list[str] = []
    if user:
        new_streak, newly_awarded = identity_service.process_game_bad_luck(
            user, is_bad=is_bad, is_jackpot=is_jackpot, current_streak=current_streak
        )
        state["bad_luck_streak"] = new_streak

    display_label = chosen["label"]
    if newly_awarded:
        display_label += f" (⚠️ Эскалация: {', '.join(newly_awarded)})"

    # Record game action
    action = LockGameAction(
        session_id=session.id,
        user_id=user_id,
        extension_type="wheel_of_fortune",
        action_title="Вращение Колеса Фортуны",
        result_code=chosen["code"],
        result_display=display_label,
        time_modifier_seconds=time_applied_sec,
        xp_modifier=chosen["xp"],
        payload={
            "sector": chosen,
            "pillory_triggered": pillory_triggered,
            "challenge_triggered": challenge_triggered,
            "challenge_info": challenge_info,
            "freeze_triggered": freeze_triggered,
            "unfreeze_triggered": unfreeze_triggered,
            "bad_luck_streak": state.get("bad_luck_streak", 0),
            "escalated_tags": newly_awarded,
        },
        created_at=now,
    )
    db.add(action)

    # Update extensions_state
    state["last_wheel_spin_at"] = now.isoformat()
    state["total_wheel_spins"] = state.get("total_wheel_spins", 0) + 1
    state["net_time_added_seconds"] = state.get("net_time_added_seconds", 0) + time_applied_sec
    session.extensions_state = state
    await db.flush()

    return {
        "success": True,
        "sector": chosen,
        "result_display": display_label,
        "time_applied_seconds": time_applied_sec,
        "xp_modifier": chosen["xp"],
        "effective_end_at": session.effective_end_at.isoformat() if session.effective_end_at else None,
        "pillory_triggered": pillory_triggered,
        "challenge_info": challenge_info,
        "freeze_triggered": freeze_triggered,
        "unfreeze_triggered": unfreeze_triggered,
        "bad_luck_streak": state.get("bad_luck_streak", 0),
        "escalated_tags": newly_awarded,
    }


async def roll_dice_of_fate(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    force: bool = False,
) -> dict:
    """Rolls 2d6 Dice of Fate for the active lock session."""
    now = datetime.now(UTC)
    session = await get_session(db, session_id, user_id)
    if session is None or session.state != "active":
        return {"success": False, "error": "Активная сессия не найдена"}

    state = dict(session.extensions_state or {})
    last_roll_str = state.get("last_dice_roll_at")
    cooldown_hours = state.get("dice_cooldown_hours", 1)

    if not force and last_roll_str:
        try:
            last_roll = datetime.fromisoformat(last_roll_str)
            if last_roll.tzinfo is None:
                last_roll = last_roll.replace(tzinfo=UTC)
            cooldown_end = last_roll + timedelta(hours=cooldown_hours)
            if now < cooldown_end:
                rem_mins = int((cooldown_end - now).total_seconds() // 60)
                return {
                    "success": False,
                    "error": f"Кубики перезаряжаются. До следующего броска осталось {rem_mins} мин.",
                    "cooldown_remaining_minutes": rem_mins,
                }
        except Exception:
            pass

    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    dice_sum = d1 + d2

    time_delta = 0
    xp_delta = 0
    result_code = f"roll_{dice_sum}"
    pillory_triggered = False

    if dice_sum == 2:
        # Snake Eyes: Critical fail
        time_delta = 14400  # +4 hours
        xp_delta = -50
        result_display = "🎲 (1+1=2) Змеиные глаза! Критический провал: +4 часа и Позорный столб!"
        pillory_triggered = True
        await send_session_to_pillory(
            db,
            session,
            reason="Кубик Судьбы: выпали Змеиные глаза (1+1)",
            details="Критический провал при броске кубиков — продление на 4 часа и позорный столб.",
        )
    elif 3 <= dice_sum <= 5:
        # Unlucky: +15 min per point
        mins_add = dice_sum * 15
        time_delta = mins_add * 60
        result_display = f"🎲 ({d1}+{d2}={dice_sum}) Неудача: добавлено +{mins_add} минут к таймеру."
    elif 6 <= dice_sum <= 8:
        # Neutral test
        result_display = f"🎲 ({d1}+{d2}={dice_sum}) Нейтрально: судьба дает вам передышку (без изменения времени)."
    elif 9 <= dice_sum <= 11:
        # Mercy: -10 min per point
        mins_sub = dice_sum * 10
        time_delta = -(mins_sub * 60)
        xp_delta = 30
        result_display = f"🎲 ({d1}+{d2}={dice_sum}) 🟢 Милосердие фортуны: сбавлено -{mins_sub} минут! (+30 XP)"
    else:  # dice_sum == 12
        # Boxcars: Jackpot!
        time_delta = -7200  # -2 hours
        xp_delta = 100
        result_display = "🎲 (6+6=12) Двойная шестерка! ДЖЕКПОТ: -2 часа от таймера и +100 XP!"

    applied_sec = 0
    if time_delta != 0:
        _, applied_sec = _apply_time_modifier_to_session(session, time_delta)

    # Bad luck streak tracking and status escalation (ADR-200)
    is_bad = (dice_sum <= 5)
    is_jackpot = (dice_sum == 12)

    user = await db.get(User, user_id)
    current_streak = state.get("bad_luck_streak", 0)
    newly_awarded: list[str] = []
    if user:
        new_streak, newly_awarded = identity_service.process_game_bad_luck(
            user, is_bad=is_bad, is_jackpot=is_jackpot, current_streak=current_streak
        )
        state["bad_luck_streak"] = new_streak

    if newly_awarded:
        result_display += f" (⚠️ Эскалация: {', '.join(newly_awarded)})"

    action = LockGameAction(
        session_id=session.id,
        user_id=user_id,
        extension_type="dice_of_fate",
        action_title="Бросок Кубиков Судьбы (2d6)",
        result_code=result_code,
        result_display=result_display,
        time_modifier_seconds=applied_sec,
        xp_modifier=xp_delta,
        payload={
            "dice_1": d1,
            "dice_2": d2,
            "sum": dice_sum,
            "pillory_triggered": pillory_triggered,
            "bad_luck_streak": state.get("bad_luck_streak", 0),
            "escalated_tags": newly_awarded,
        },
        created_at=now,
    )
    db.add(action)

    state["last_dice_roll_at"] = now.isoformat()
    state["total_dice_rolls"] = state.get("total_dice_rolls", 0) + 1
    state["net_time_added_seconds"] = state.get("net_time_added_seconds", 0) + applied_sec
    session.extensions_state = state
    await db.flush()

    return {
        "success": True,
        "dice_1": d1,
        "dice_2": d2,
        "sum": dice_sum,
        "result_display": result_display,
        "time_applied_seconds": applied_sec,
        "xp_modifier": xp_delta,
        "effective_end_at": session.effective_end_at.isoformat() if session.effective_end_at else None,
        "pillory_triggered": pillory_triggered,
        "bad_luck_streak": state.get("bad_luck_streak", 0),
        "escalated_tags": newly_awarded,
    }


async def start_obedience_challenge(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    challenge_type: str | None = None,
) -> dict:
    """Initiates an obedience & humiliation challenge with a single-use verification code."""
    now = datetime.now(UTC)
    session = await get_session(db, session_id, user_id)
    if session is None or session.state != "active":
        return {"success": False, "error": "Активная сессия не найдена"}

    state = dict(session.extensions_state or {})
    active = state.get("active_challenge")
    if active:
        # Check if already active and not expired
        exp_str = active.get("expires_at")
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=UTC)
                if now < exp_dt:
                    return {
                        "success": False,
                        "error": "У вас уже есть активное испытание. Завершите его или сдайтесь.",
                        "active_challenge": active,
                    }
            except Exception:
                pass

    # Pick challenge
    if challenge_type and challenge_type in OBEDIENCE_CHALLENGES:
        tpl = OBEDIENCE_CHALLENGES[challenge_type]
    else:
        tpl = random.choice(list(OBEDIENCE_CHALLENGES.values()))

    # Create verification challenge (single-use code with HMAC)
    challenge, code = await create_session_verification_challenge(
        db,
        session_id=session.id,
        owner_id=user_id,
        ttl_minutes=tpl["duration_minutes"],
        code_length=6,
    )

    challenge_data = {
        "id": str(challenge.id),
        "type": tpl["type"],
        "title": tpl["title"],
        "badge": tpl["badge"],
        "description": tpl["description"],
        "verification_code": code,
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=tpl["duration_minutes"])).isoformat(),
        "duration_minutes": tpl["duration_minutes"],
        "reward_seconds": tpl["reward_seconds"],
        "reward_xp": tpl["reward_xp"],
        "penalty_seconds": tpl["penalty_seconds"],
        "penalty_xp": tpl["penalty_xp"],
        "pillory_on_fail": tpl["pillory_on_fail"],
    }

    state["active_challenge"] = challenge_data
    session.extensions_state = state

    user = await db.get(User, user_id)
    if user:
        identity_service.on_challenge_started(user)

    action = LockGameAction(
        session_id=session.id,
        user_id=user_id,
        extension_type="obedience_challenge",
        action_title=f"Начато испытание: {tpl['title']}",
        result_code=tpl["type"],
        result_display=f"Испытание '{tpl['title']}'. Разовый код: {code}. Срок: {tpl['duration_minutes']} мин.",
        time_modifier_seconds=0,
        xp_modifier=0,
        payload=challenge_data,
        created_at=now,
    )
    db.add(action)
    await db.flush()

    return {"success": True, "challenge": challenge_data}


async def complete_obedience_challenge(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    tag_number: str,
    verification_code: str,
    photo_notes: str | None = None,
) -> dict:
    """Completes active obedience challenge by verifying single-use code and seal tag."""
    now = datetime.now(UTC)
    session = await get_session(db, session_id, user_id)
    if session is None or session.state != "active":
        return {"success": False, "error": "Активная сессия не найдена"}

    state = dict(session.extensions_state or {})
    active = state.get("active_challenge")
    if not active:
        return {"success": False, "error": "Нет активного испытания для завершения"}

    # Verify submission code
    verify_res = await verify_session_photo_submission(
        db,
        session_id=session_id,
        owner_id=user_id,
        tag_number=tag_number,
        verification_code=verification_code,
        notes=f"Испытание '{active['title']}': {photo_notes or ''}".strip(),
    )
    if not verify_res.get("success"):
        return verify_res

    # If session was frozen, successfully completing challenge unfreezes it!
    if session.is_frozen:
        await unfreeze_session_timer(db, session.id, user_id, reason="challenge_completed")

    # Apply rewards
    reward_sec = active.get("reward_seconds", -1800)
    reward_xp = active.get("reward_xp", 50)
    _, applied_sec = _apply_time_modifier_to_session(session, reward_sec)

    mins_reduced = abs(applied_sec) // 60
    action = LockGameAction(
        session_id=session.id,
        user_id=user_id,
        extension_type="obedience_challenge",
        action_title=f"Испытание сдано: {active['title']}",
        result_code="challenge_completed",
        result_display=(
            f"✅ Испытание '{active['title']}' выполнено! "
            f"Сбавлено {mins_reduced} мин, начислено +{reward_xp} XP."
        ),
        time_modifier_seconds=applied_sec,
        xp_modifier=reward_xp,
        payload={
            "challenge": active,
            "tag_number": tag_number,
            "verification_code": verification_code,
            "photo_notes": photo_notes,
        },
        created_at=now,
    )
    db.add(action)

    # Clear active challenge and redeem bad luck streak
    state["active_challenge"] = None
    state["total_challenges_completed"] = state.get("total_challenges_completed", 0) + 1
    state["bad_luck_streak"] = 0
    session.extensions_state = state

    user = await db.get(User, user_id)
    if user:
        identity_service.on_challenge_outcome(user, success=True)

    await db.flush()

    return {
        "success": True,
        "title": active["title"],
        "time_applied_seconds": applied_sec,
        "reward_xp": reward_xp,
        "effective_end_at": session.effective_end_at.isoformat() if session.effective_end_at else None,
    }


async def fail_obedience_challenge(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str = "surrender",
) -> dict:
    """Fails or surrenders active obedience challenge with discipline penalties."""
    now = datetime.now(UTC)
    session = await get_session(db, session_id, user_id)
    if session is None or session.state != "active":
        return {"success": False, "error": "Активная сессия не найдена"}

    state = dict(session.extensions_state or {})
    active = state.get("active_challenge")
    if not active:
        return {"success": False, "error": "Нет активного испытания для отказа"}

    penalty_sec = active.get("penalty_seconds", 7200)
    penalty_xp = active.get("penalty_xp", -50)
    _, applied_sec = _apply_time_modifier_to_session(session, penalty_sec)

    pillory_triggered = False
    if active.get("pillory_on_fail"):
        pillory_triggered = True
        await send_session_to_pillory(
            db,
            session,
            reason=f"Провал испытания: {active['title']}",
            details=f"Пользователь отказался от испытания послушания ('{reason}'). Назначено штрафное время.",
        )

    mins_added = applied_sec // 60
    action = LockGameAction(
        session_id=session.id,
        user_id=user_id,
        extension_type="obedience_challenge",
        action_title=f"Испытание провалено: {active['title']}",
        result_code="challenge_failed",
        result_display=(
            f"❌ Провал испытания '{active['title']}' ({reason}). "
            f"Штраф +{mins_added} мин к таймеру, {penalty_xp} XP."
        ),
        time_modifier_seconds=applied_sec,
        xp_modifier=penalty_xp,
        payload={"challenge": active, "reason": reason, "pillory_triggered": pillory_triggered},
        created_at=now,
    )
    db.add(action)

    state["active_challenge"] = None
    state["total_challenges_failed"] = state.get("total_challenges_failed", 0) + 1
    session.extensions_state = state

    user = await db.get(User, user_id)
    if user:
        identity_service.on_challenge_outcome(user, success=False)

    await db.flush()

    return {
        "success": True,
        "title": active["title"],
        "time_applied_seconds": applied_sec,
        "penalty_xp": penalty_xp,
        "pillory_triggered": pillory_triggered,
        "effective_end_at": session.effective_end_at.isoformat() if session.effective_end_at else None,
    }


async def trigger_time_jump(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """AI Keyholder random time jump / temporal anomaly (-30 min to +90 min)."""
    now = datetime.now(UTC)
    session = await get_session(db, session_id, user_id)
    if session is None or session.state != "active":
        return {"success": False, "error": "Активная сессия не найдена"}

    jumps = [-1800, -900, 1800, 3600, 5400]  # -30m, -15m, +30m, +60m, +90m
    jump_sec = random.choice(jumps)

    _, applied_sec = _apply_time_modifier_to_session(session, jump_sec)
    mins = abs(applied_sec) // 60
    if applied_sec >= 0:
        res_text = f"⏳ Временная аномалия ИИ: стрелки часов сдвинуты вперед на +{mins} минут."
    else:
        res_text = f"⏳ Временная аномалия ИИ: стрелки часов сдвинуты назад на -{mins} минут (бонус милосердия)."

    action = LockGameAction(
        session_id=session.id,
        user_id=user_id,
        extension_type="time_jump",
        action_title="Временная аномалия ИИ-Ключника",
        result_code="time_jump",
        result_display=res_text,
        time_modifier_seconds=applied_sec,
        xp_modifier=0,
        payload={"jump_seconds": jump_sec},
        created_at=now,
    )
    db.add(action)

    state = dict(session.extensions_state or {})
    state["last_time_jump_at"] = now.isoformat()
    session.extensions_state = state
    await db.flush()

    return {
        "success": True,
        "result_display": res_text,
        "time_applied_seconds": applied_sec,
        "effective_end_at": session.effective_end_at.isoformat() if session.effective_end_at else None,
    }


async def get_game_actions_history(
    db: AsyncSession,
    session_id: uuid.UUID,
    limit: int = 15,
) -> list[LockGameAction]:
    """Returns recent game action history for session."""
    stmt = (
        select(LockGameAction)
        .where(LockGameAction.session_id == session_id)
        .order_by(LockGameAction.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def freeze_session_timer(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str = "manual",
) -> dict:
    """Permanently freezes lock session timer (time stops countdown)."""
    now = datetime.now(UTC)
    session = await get_session(db, session_id, user_id)
    if session is None or session.state != "active":
        return {"success": False, "error": "Активная сессия не найдена"}

    if session.is_frozen:
        return {
            "success": True,
            "already_frozen": True,
            "frozen_remaining_seconds": session.frozen_remaining_seconds,
        }

    eff_end = as_utc(session.effective_end_at) if session.effective_end_at else now + timedelta(hours=24)
    rem_sec = max(0, int((eff_end - now).total_seconds()))

    session.is_frozen = True
    session.frozen_at = now
    session.frozen_remaining_seconds = rem_sec

    # Log game action
    action = LockGameAction(
        session_id=session.id,
        user_id=user_id,
        extension_type="timer_freeze",
        action_title="Перманентная заморозка таймера",
        result_code="frozen",
        result_display=f"❄️ Таймер заморожен на остатке {rem_sec // 60} мин. Ход времени остановлен ({reason}).",
        time_modifier_seconds=0,
        xp_modifier=-20 if reason != "manual" else 0,
        payload={"remaining_seconds": rem_sec, "reason": reason},
        created_at=now,
    )
    db.add(action)

    # Log wear event
    from app.models.wear_events import WearEventLog

    w_log = WearEventLog(
        user_id=user_id,
        device_id=session.device_id,
        session_id=session.id,
        event_code="timer_freeze",
        state_before="locked" if session.is_currently_locked else "unlocked",
        state_after="locked" if session.is_currently_locked else "unlocked",
        user_comment=f"Перманентная заморозка таймера: {reason}",
        reactions_applied={"frozen_remaining_seconds": rem_sec},
        created_at=now,
    )
    db.add(w_log)

    user = await db.get(User, user_id)
    if user:
        identity_service.on_timer_frozen(user)

    await db.flush()

    return {
        "success": True,
        "is_frozen": True,
        "frozen_remaining_seconds": rem_sec,
        "result_display": action.result_display,
    }


async def unfreeze_session_timer(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str = "manual",
) -> dict:
    """Unfreezes previously frozen lock session timer (resumes countdown)."""
    now = datetime.now(UTC)
    session = await get_session(db, session_id, user_id)
    if session is None or session.state != "active":
        return {"success": False, "error": "Активная сессия не найдена"}

    if not session.is_frozen:
        return {
            "success": True,
            "already_unfrozen": True,
            "effective_end_at": session.effective_end_at.isoformat() if session.effective_end_at else None,
        }

    rem_sec = session.frozen_remaining_seconds or 3600
    new_end = now + timedelta(seconds=rem_sec)

    session.is_frozen = False
    session.frozen_at = None
    session.frozen_remaining_seconds = None
    session.effective_end_at = new_end

    action = LockGameAction(
        session_id=session.id,
        user_id=user_id,
        extension_type="timer_unfreeze",
        action_title="Разморозка таймера",
        result_code="unfrozen",
        result_display=(
            f"🔥 Таймер разморожен! Ход времени возобновлен, "
            f"новое завершение: {new_end.strftime('%d.%m %H:%M')}."
        ),
        time_modifier_seconds=0,
        xp_modifier=30,
        payload={"resumed_seconds": rem_sec, "reason": reason},
        created_at=now,
    )
    db.add(action)

    from app.models.wear_events import WearEventLog

    w_log = WearEventLog(
        user_id=user_id,
        device_id=session.device_id,
        session_id=session.id,
        event_code="timer_unfreeze",
        state_before="locked" if session.is_currently_locked else "unlocked",
        state_after="locked" if session.is_currently_locked else "unlocked",
        user_comment=f"Разморозка таймера: {reason}",
        reactions_applied={"resumed_remaining_seconds": rem_sec},
        created_at=now,
    )
    db.add(w_log)

    user = await db.get(User, user_id)
    if user:
        identity_service.on_timer_unfrozen(user)

    await db.flush()

    return {
        "success": True,
        "is_frozen": False,
        "effective_end_at": new_end.isoformat(),
        "result_display": action.result_display,
    }
