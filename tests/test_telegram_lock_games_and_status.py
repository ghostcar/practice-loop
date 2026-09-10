"""Unit and integration tests for Telegram Lock Extensions, Status tags, and Photo Submissions (ADR-201).

Covers:
- get_wear_card_keyboard dynamic buttons (Wheel, Dice, Freeze/Unfreeze, Challenges)
- _render_wear_card with status tags, bad luck streak warning, frozen badge, active challenge
- _render_user_status_card with identity, roles, and 3-tier status tags (permanent, standing, dynamic)
- Mini-game callback handlers (Wheel of Fortune, Dice of Fate)
- Permanent freeze and unfreeze toggle callbacks
- Photo submission handling for obedience challenges and seal inspections
- Voluntary emulation fallback for challenges (ADR-129)
- Telegram PUSH notification on status tag escalation
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer.services import gamification_extensions_service as game_svc
from app.models.locktimer import LockSession
from app.models.user import User
from app.services import identity_service
from app.telegram.keyboards import get_wear_card_keyboard
from app.telegram.personal_contour import (
    _render_user_status_card,
    _render_wear_card,
    cb_wear_freeze,
    cb_wear_game_dice,
    cb_wear_game_wheel,
    cb_wear_unfreeze,
    msg_challenge_photo,
    msg_challenge_text_fallback,
    msg_wear_inspection_photo,
)


def test_wear_card_keyboard_extensions():
    """Verify that wear card keyboard includes Wheel, Dice, Freeze/Unfreeze, and Challenge buttons."""
    # Active, not frozen, no challenge
    kb = get_wear_card_keyboard(is_active=True, is_locked=True, is_frozen=False, has_challenge=False)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "wear_game_wheel" in callbacks
    assert "wear_game_dice" in callbacks
    assert "wear_freeze" in callbacks
    assert "wear_unfreeze" not in callbacks
    assert "wear_game_challenge" in callbacks
    assert "wear_challenge_submit" not in callbacks

    # Active, frozen, active challenge
    kb_frozen = get_wear_card_keyboard(is_active=True, is_locked=True, is_frozen=True, has_challenge=True)
    frozen_callbacks = [btn.callback_data for row in kb_frozen.inline_keyboard for btn in row]
    assert "wear_game_wheel" in frozen_callbacks
    assert "wear_game_dice" in frozen_callbacks
    assert "wear_unfreeze" in frozen_callbacks
    assert "wear_freeze" not in frozen_callbacks
    assert "wear_challenge_submit" in frozen_callbacks
    assert "wear_challenge_surrender" in frozen_callbacks
    assert "wear_game_challenge" not in frozen_callbacks


def test_render_wear_card_with_tags_and_streak():
    """Verify that _render_wear_card formats status tags, streak warnings, and challenge details."""
    user = User(

        id=uuid.uuid4(),
        email="test_sub@example.com",
        display_name="Алекс",
        status_tags={
            "permanent": ["collared", "pathetic_loser"],
            "standing": ["chastity_locked", "frozen_timer"],
            "dynamic": ["unlucky"],
        },
    )

    session = LockSession(
        id=uuid.uuid4(),
        owner_id=user.id,
        state="active",
        mode="open_ended",
        is_frozen=True,
        extensions_state={
            "bad_luck_streak": 3,
            "active_challenge": {
                "title": "Покаяние на коленях",
                "verification_code": "CHK882",
                "reward_seconds": -1800,
                "reward_xp": 50,
            },
        },
    )

    status = {
        "session": session,
        "device": None,
        "supports_tag": True,
        "is_active": True,
        "is_locked": True,
        "current_tag": "SEAL-100",
        "last_comfort": 4,
        "time_text": "❄️ ТАЙМЕР ЗАМОРОЖЕН: 02:00:00",
        "deadline_text": "",
        "upcoming_slots": [],
    }

    text, kb = _render_wear_card(status, is_agent_mode=False, user=user)

    # Check tags
    assert "#collared" in text
    assert "#pathetic_loser" in text
    assert "#chastity_locked" in text
    assert "Хронический неудачник" in text

    # Check freeze and timer
    assert "ЗАМОРОЖЕН" in text
    assert "02:00:00" in text

    # Check bad luck streak
    assert "Полоса неудач" in text
    assert "3 поражений подряд" in text

    # Check challenge info
    assert "АКТИВНО ИСПЫТАНИЕ ПОСЛУШАНИЯ" in text
    assert "Покаяние на коленях" in text
    assert "CHK882" in text

    # Check keyboard has unfreeze and submit buttons
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "wear_unfreeze" in callbacks
    assert "wear_challenge_submit" in callbacks


def test_render_user_status_card():
    """Verify _render_user_status_card shows identity, roles, and categorized status tags."""
    user = User(
        id=uuid.uuid4(),
        email="sub@example.com",
        display_name="Роман",
        portal_name="Лика",
        ai_designation="SUB-42",
        primary_role="submissive",
        portal_roles=["pet", "chastity_captive"],
        status_tags={
            "permanent": ["pathetic_loser"],
            "standing": ["chastity_locked", "frozen_timer"],
            "dynamic": ["unlucky", "under_trial"],
        },
    )

    session = LockSession(
        id=uuid.uuid4(),
        owner_id=user.id,
        state="active",
        is_frozen=True,
        extensions_state={"bad_luck_streak": 2},
    )

    status = {
        "session": session,
        "is_active": True,
        "is_locked": True,
        "current_tag": "TAG-99",
        "time_text": "01:30:00",
    }

    text, kb = _render_user_status_card(user, status)

    assert "Лика (SUB-42)" in text
    assert "Ведомый / Нижний" in text
    assert "Питомец" in text
    assert "Хронический неудачник" in text
    assert "Время заморожено" in text
    assert "Полоса неудач" in text
    assert "Серия неудач в играх: **2** подряд" in text

    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "wear_refresh" in callbacks
    assert "status_refresh" in callbacks


@pytest.mark.asyncio
async def test_wear_game_wheel_callback(db_session: AsyncSession):
    """Test spinning the Wheel of Fortune through telegram callback."""
    now = datetime.now(UTC)
    user = User(
        id=uuid.uuid4(),
        email="wheel_test@example.com",
        password_hash="hash",
        telegram_chat_id=1234567,
    )
    db_session.add(user)

    session = LockSession(
        id=uuid.uuid4(),
        owner_id=user.id,
        state="active",
        mode="open_ended",
        is_currently_locked=True,
        started_at=now,
        random_seed_encrypted="seed",
        random_seed_commitment="commit",
        extensions_state={},
    )
    db_session.add(session)
    await db_session.commit()

    # Create mock callback
    callback = AsyncMock()
    callback.message.chat.id = 1234567
    callback.message.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})

    with (
        patch("app.telegram.pc.games._get_user_by_chat", return_value=user),
        patch("app.telegram.pc.games.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        await cb_wear_game_wheel(callback, state)

    callback.message.answer.assert_called_once()
    sent_text = callback.message.answer.call_args[0][0]
    assert "Колесо Фортуны сделало оборот" in sent_text
    callback.answer.assert_called_with("🎡 Колесо прокручено!")


@pytest.mark.asyncio
async def test_wear_game_dice_callback(db_session: AsyncSession):
    """Test rolling Dice of Fate through telegram callback."""
    now = datetime.now(UTC)
    user = User(
        id=uuid.uuid4(),
        email="dice_test@example.com",
        password_hash="hash",
        telegram_chat_id=7654321,
    )
    db_session.add(user)

    session = LockSession(
        id=uuid.uuid4(),
        owner_id=user.id,
        state="active",
        mode="open_ended",
        is_currently_locked=True,
        started_at=now,
        random_seed_encrypted="seed",
        random_seed_commitment="commit",
        extensions_state={},
    )
    db_session.add(session)
    await db_session.commit()

    callback = AsyncMock()
    callback.message.chat.id = 7654321
    callback.message.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})

    with (
        patch("app.telegram.pc.games._get_user_by_chat", return_value=user),
        patch("app.telegram.pc.games.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        await cb_wear_game_dice(callback, state)

    callback.message.answer.assert_called_once()
    sent_text = callback.message.answer.call_args[0][0]
    assert "Бросок Кубиков Судьбы" in sent_text
    callback.answer.assert_called_with("🎲 Бросок совершен!")


@pytest.mark.asyncio
async def test_wear_freeze_and_unfreeze_callbacks(db_session: AsyncSession):
    """Test freezing and unfreezing lock timer via Telegram callbacks."""
    now = datetime.now(UTC)
    user = User(
        id=uuid.uuid4(),
        email="freeze_tg@example.com",
        password_hash="hash",
        telegram_chat_id=999888,
    )
    db_session.add(user)

    session = LockSession(
        id=uuid.uuid4(),
        owner_id=user.id,
        state="active",
        mode="scheduled",
        effective_end_at=now + timedelta(hours=5),
        is_frozen=False,
        random_seed_encrypted="seed",
        random_seed_commitment="commit",
    )
    db_session.add(session)
    await db_session.commit()

    callback = AsyncMock()
    callback.message.chat.id = 999888
    callback.message.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})

    with (
        patch("app.telegram.pc.games._get_user_by_chat", return_value=user),
        patch("app.telegram.pc.games.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        # Freeze
        await cb_wear_freeze(callback, state)
        assert session.is_frozen is True

        # Unfreeze
        await cb_wear_unfreeze(callback, state)
        assert session.is_frozen is False



@pytest.mark.asyncio
async def test_challenge_photo_submission_flow(db_session: AsyncSession):
    """Test submitting photo to complete active obedience challenge via Telegram."""
    now = datetime.now(UTC)
    user = User(
        id=uuid.uuid4(),
        email="photo_challenge@example.com",
        password_hash="hash",
        telegram_chat_id=555444,
        status_tags={"dynamic": ["unlucky", "under_trial"]},
    )
    db_session.add(user)

    session = LockSession(
        id=uuid.uuid4(),
        owner_id=user.id,
        state="active",
        current_tag_number="TAG-777",
        effective_end_at=now + timedelta(hours=10),
        random_seed_encrypted="seed",
        random_seed_commitment="commit",
        extensions_state={},
    )
    db_session.add(session)
    await db_session.commit()

    # Start challenge
    ch_res = await game_svc.start_obedience_challenge(db_session, session.id, user.id, "kneeling_repentance")
    await db_session.commit()
    assert ch_res["success"] is True

    # Simulate user sending photo
    msg = AsyncMock()
    msg.chat.id = 555444
    msg.photo = [MagicMock(file_id="photo_file_123")]
    msg.caption = "Отчет с кодом"
    msg.answer = AsyncMock()

    fsm_state = AsyncMock()
    fsm_state.get_data = AsyncMock(return_value={})
    fsm_state.set_state = AsyncMock()

    with (
        patch("app.telegram.pc.games._get_user_by_chat", return_value=user),
        patch("app.telegram.pc.games.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        await msg_challenge_photo(msg, fsm_state)

    fsm_state.set_state.assert_called_with(None)
    assert msg.answer.call_count >= 1
    sent_text = msg.answer.call_args_list[0][0][0]
    assert "успешно принято и зачтено" in sent_text
    assert "#obedient" in sent_text

    # Verify session active challenge was cleared
    assert session.extensions_state.get("active_challenge") is None
    # Verify user received #obedient tag and lost #unlucky
    assert identity_service.has_status_tag(user, "obedient")
    assert not identity_service.has_status_tag(user, "unlucky")


@pytest.mark.asyncio
async def test_challenge_text_emulation_fallback(db_session: AsyncSession):
    """Test text emulation fallback for challenge submission under ADR-129."""
    now = datetime.now(UTC)
    user = User(
        id=uuid.uuid4(),
        email="emul_challenge@example.com",
        password_hash="hash",
        telegram_chat_id=111222,
    )
    db_session.add(user)

    session = LockSession(
        id=uuid.uuid4(),
        owner_id=user.id,
        state="active",
        current_tag_number="TAG-111",
        effective_end_at=now + timedelta(hours=10),
        random_seed_encrypted="seed",
        random_seed_commitment="commit",
        extensions_state={},
    )
    db_session.add(session)
    await db_session.commit()

    await game_svc.start_obedience_challenge(db_session, session.id, user.id, "deep_kowtow")
    await db_session.commit()

    msg = AsyncMock()
    msg.chat.id = 111222
    msg.text = "Выполнил поклон на коленях перед зеркалом"
    msg.answer = AsyncMock()

    fsm_state = AsyncMock()
    fsm_state.get_data = AsyncMock(return_value={})
    fsm_state.set_state = AsyncMock()

    with (
        patch("app.telegram.pc.games._get_user_by_chat", return_value=user),
        patch("app.telegram.pc.games.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        await msg_challenge_text_fallback(msg, fsm_state)

    fsm_state.set_state.assert_called_with(None)
    sent_text = msg.answer.call_args_list[0][0][0]
    assert "зачтено (эмуляция)" in sent_text
    assert session.extensions_state.get("active_challenge") is None


@pytest.mark.asyncio
async def test_wear_inspection_photo_submission(db_session: AsyncSession):
    """Test seal tag inspection photo submission."""
    user = User(
        id=uuid.uuid4(),
        email="inspect_photo@example.com",
        password_hash="hash",
        telegram_chat_id=333444,
    )
    db_session.add(user)

    session = LockSession(
        id=uuid.uuid4(),
        owner_id=user.id,
        state="active",
        current_tag_number="SEAL-42",
        random_seed_encrypted="seed",
        random_seed_commitment="commit",
    )
    db_session.add(session)
    await db_session.commit()

    msg = AsyncMock()
    msg.chat.id = 333444
    msg.photo = [MagicMock(file_id="seal_photo_file")]
    msg.caption = "SEAL-42"
    msg.answer = AsyncMock()

    fsm_state = AsyncMock()
    fsm_state.get_data = AsyncMock(return_value={})
    fsm_state.set_state = AsyncMock()

    with (
        patch("app.telegram.pc.games._get_user_by_chat", return_value=user),
        patch("app.telegram.pc.games.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        await msg_wear_inspection_photo(msg, fsm_state)


    sent_text = msg.answer.call_args_list[0][0][0]
    assert "Фотоконтроль пломбы зарегистрирован" in sent_text
    assert "SEAL-42" in sent_text


@pytest.mark.asyncio
async def test_notify_status_escalation():
    """Verify asynchronous Telegram notification is triggered on status tag escalation."""
    user = User(
        id=uuid.uuid4(),
        email="notify_user@example.com",
        telegram_chat_id=888777,
    )

    with patch("app.telegram.bot.send_telegram_notification", new_callable=AsyncMock) as mock_send:
        await identity_service.notify_status_escalation(user, ["#pathetic_loser"], 4)
        mock_send.assert_called_once()
        chat_id, text = mock_send.call_args[0]
        assert chat_id == 888777
        assert "Эскалация статуса в сессии пояса" in text
        assert "#pathetic_loser" in text
        assert "4" in text
