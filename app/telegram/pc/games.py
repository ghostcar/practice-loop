"""Personal Contour — Mini-games & Photo confirmations (ADR-198, ADR-199, ADR-201)."""

from __future__ import annotations

import contextlib

from aiogram import F, types
from aiogram.fsm.context import FSMContext

from app.database import async_session_factory
from app.locktimer.services import gamification_extensions_service as game_svc
from app.services import wear_reactive_service as wear_svc
from app.telegram.pc.helpers import (
    PersonalStates,
    _get_user_by_chat,
    personal_router,
)
from app.telegram.pc.wear import _render_wear_card


@personal_router.callback_query(F.data == "wear_game_wheel")
async def cb_wear_game_wheel(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        session = await wear_svc.get_active_wear_session(db, user.id)
        if not session:
            await callback.answer("Нет активной сессии ношения для Колеса Фортуны", show_alert=True)
            return

        res = await game_svc.spin_wheel_of_fortune(db, session.id, user.id)
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    if not res.get("success"):
        await callback.answer(f"⚠️ {res.get('error')}", show_alert=True)
        return

    report_lines = [
        "🎡 **Колесо Фортуны сделало оборот!**\n",
        f"🎯 Сектор: **{res.get('sector', {}).get('label', 'Исход')}**",
        f"📜 Результат: {res.get('result_display', '')}",
    ]

    escalated = res.get("escalated_tags") or []
    streak = res.get("bad_luck_streak", 0)
    if escalated:
        tags_str = " ".join([f"`{t}`" for t in escalated])
        report_lines.append(f"\n⚠️ **Эскалация статуса:** Вам присвоен статус {tags_str}!")
    if streak >= 2:
        report_lines.append(f"⚠️ Серия неудач: **{streak}** подряд.")

    await callback.message.answer("\n".join(report_lines), parse_mode="Markdown")

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer("🎡 Колесо прокручено!")


@personal_router.callback_query(F.data == "wear_game_dice")
async def cb_wear_game_dice(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        session = await wear_svc.get_active_wear_session(db, user.id)
        if not session:
            await callback.answer("Нет активной сессии ношения для Кубиков Судьбы", show_alert=True)
            return

        res = await game_svc.roll_dice_of_fate(db, session.id, user.id)
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    if not res.get("success"):
        await callback.answer(f"⚠️ {res.get('error')}", show_alert=True)
        return

    payload = res.get("payload") or {}
    d1 = payload.get("dice_1", "?")
    d2 = payload.get("dice_2", "?")
    d_sum = payload.get("sum", "?")

    report_lines = [
        "🎲 **Бросок Кубиков Судьбы (2d6)**\n",
        f"🎲 Выпало: `[{d1}]` + `[{d2}]` = **{d_sum}**",
        f"📜 Исход: {res.get('result_display', '')}",
    ]

    escalated = res.get("escalated_tags") or []
    streak = res.get("bad_luck_streak", 0)
    if escalated:
        tags_str = " ".join([f"`{t}`" for t in escalated])
        report_lines.append(f"\n⚠️ **Эскалация статуса:** Вам присвоен статус {tags_str}!")
    if streak >= 2:
        report_lines.append(f"⚠️ Серия неудач: **{streak}** подряд.")

    await callback.message.answer("\n".join(report_lines), parse_mode="Markdown")

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer("🎲 Бросок совершен!")


@personal_router.callback_query(F.data == "wear_freeze")
async def cb_wear_freeze(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        session = await wear_svc.get_active_wear_session(db, user.id)
        if not session:
            await callback.answer("Нет активной сессии для заморозки", show_alert=True)
            return

        res = await game_svc.freeze_session_timer(
            db, session.id, user.id, reason="Заморозка через Telegram-бота"
        )
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    if not res.get("success"):
        await callback.answer(f"⚠️ {res.get('error')}", show_alert=True)
        return

    await callback.message.answer(
        "❄️ **Таймер сессии успешно заморожен!**\n"
        "Ход времени остановлен. Таймер зафиксирован до выполнения разморозки.",
        parse_mode="Markdown",
    )

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer("❄️ Таймер заморожен")


@personal_router.callback_query(F.data == "wear_unfreeze")
async def cb_wear_unfreeze(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        session = await wear_svc.get_active_wear_session(db, user.id)
        if not session:
            await callback.answer("Нет активной сессии для разморозки", show_alert=True)
            return

        res = await game_svc.unfreeze_session_timer(
            db, session.id, user.id, reason="Разморозка через Telegram-бота"
        )
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    if not res.get("success"):
        await callback.answer(f"⚠️ {res.get('error')}", show_alert=True)
        return

    await callback.message.answer(
        "🔥 **Таймер разморожен!**\n"
        "Обратный отсчет возобновлен с сохраненного остатка времени.",
        parse_mode="Markdown",
    )

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer("🔥 Таймер разморожен")


@personal_router.callback_query(F.data == "wear_game_challenge")
async def cb_wear_game_challenge(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        session = await wear_svc.get_active_wear_session(db, user.id)
        if not session:
            await callback.answer("Нет активной сессии ношения для испытания", show_alert=True)
            return

        res = await game_svc.start_obedience_challenge(db, session.id, user.id)
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    if not res.get("success"):
        await callback.answer(f"⚠️ {res.get('error')}", show_alert=True)
        return

    ch = res.get("challenge", {})
    r_mins = abs(ch.get("reward_seconds", 0)) // 60
    p_mins = ch.get("penalty_seconds", 0) // 60

    challenge_text = (
        f"🎭 **Начато испытание послушания:** *{ch.get('title')}*\n\n"
        f"📝 **Задание:**\n{ch.get('description')}\n\n"
        f"🔑 **Разовый проверочный код:** `{ch.get('verification_code')}`\n"
        f"⏱ **Срок выполнения:** {ch.get('duration_minutes')} минут\n"
        f"🏆 **Награда при сдаче:** -{r_mins} мин к таймеру, +{ch.get('reward_xp')} XP\n"
        f"⚠️ **Штраф при отказе:** +{p_mins} мин к таймеру, {ch.get('penalty_xp')} XP\n\n"
        f"📸 _Сделайте фото с кодом и отправьте прямо в этот чат!_"
    )
    await callback.message.answer(challenge_text, parse_mode="Markdown")

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer("🎭 Испытание получено!")


@personal_router.callback_query(F.data == "wear_challenge_submit")
async def cb_wear_challenge_submit(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PersonalStates.waiting_for_challenge_photo)
    await callback.message.answer(
        "📸 **Сдача фото-испытания послушания**\n\n"
        "Отправьте фотографию выполнения задания прямо в этот чат.\n"
        "На фото должны быть четко видны пояс, разовый проверочный код и выполнение условий задания.\n\n"
        "_(Если нет возможности сделать фото, отправьте текстовое подтверждение для эмуляции по ADR-129)_",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.callback_query(F.data == "wear_challenge_surrender")
async def cb_wear_challenge_surrender(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        session = await wear_svc.get_active_wear_session(db, user.id)
        if not session:
            await callback.answer("Сессия не найдена", show_alert=True)
            return

        res = await game_svc.fail_obedience_challenge(db, session.id, user.id, reason="surrender")
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    if not res.get("success"):
        await callback.answer(f"⚠️ {res.get('error')}", show_alert=True)
        return

    p_mins = res.get("time_applied_seconds", 0) // 60
    await callback.message.answer(
        f"🏳️ **Вы сдались и отказались от испытания.**\n\n"
        f"⏱ Наложено штрафное время: **+{p_mins} мин**\n"
        f"⚠️ Штраф дисциплины: **{res.get('penalty_xp')} XP**\n"
        f"🏷 Присвоен статус: `#disobedient`",
        parse_mode="Markdown",
    )

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer("Отказ зафиксирован")


# ── Photo confirmations (ADR-201) ──────────────────────────────────────────


@personal_router.message(PersonalStates.waiting_for_challenge_photo, F.photo)
async def msg_challenge_photo(message: types.Message, state: FSMContext):
    """Handles photo submission for active obedience challenge."""
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    photo = message.photo[-1]
    photo_file_id = photo.file_id
    caption = (message.caption or "").strip()

    async with async_session_factory() as db:
        session = await wear_svc.get_active_wear_session(db, user.id)
        if not session:
            await state.set_state(None)
            await message.answer("❌ Активная сессия ношения не найдена.")
            return

        extensions_state = dict(session.extensions_state or {})
        active = extensions_state.get("active_challenge")
        if not active:
            await state.set_state(None)
            await message.answer("❌ Нет активного испытания для сдачи.")
            return

        verification_code = active.get("verification_code", "")
        tag_number = session.current_tag_number or "verified"

        res = await game_svc.complete_obedience_challenge(
            db,
            session_id=session.id,
            user_id=user.id,
            tag_number=tag_number,
            verification_code=verification_code,
            photo_notes=f"TG photo {photo_file_id}. {caption}".strip(),
        )
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)
    if res.get("success"):
        mins = abs(res.get("time_applied_seconds", 0)) // 60
        xp = res.get("reward_xp", 0)
        await message.answer(
            f"🎉 **Испытание '{res.get('title')}' успешно принято и зачтено!**\n\n"
            f"⏱ Сокращение таймера: **-{mins} мин**\n"
            f"💎 Начислено: **+{xp} XP**\n"
            f"❄️ Заморозка таймера (если была) растоплена покорностью!\n"
            f"🍀 Серия неудач сброшена, сняты статусы `#unlucky` и `#loser`.\n"
            f"🏷 Присвоен статус: `#obedient`",
            parse_mode="Markdown",
        )
    else:
        await message.answer(f"⚠️ Ошибка при подтверждении: {res.get('error')}", parse_mode="Markdown")

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.message(PersonalStates.waiting_for_challenge_photo)
async def msg_challenge_text_fallback(message: types.Message, state: FSMContext):
    """Voluntary emulation fallback for obedience challenge (ADR-129)."""
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    text_notes = (message.text or "").strip()

    async with async_session_factory() as db:
        session = await wear_svc.get_active_wear_session(db, user.id)
        if not session:
            await state.set_state(None)
            await message.answer("❌ Активная сессия ношения не найдена.")
            return

        extensions_state = dict(session.extensions_state or {})
        active = extensions_state.get("active_challenge")
        if not active:
            await state.set_state(None)
            await message.answer("❌ Нет активного испытания для сдачи.")
            return

        verification_code = active.get("verification_code", "")
        tag_number = session.current_tag_number or "verified"

        res = await game_svc.complete_obedience_challenge(
            db,
            session_id=session.id,
            user_id=user.id,
            tag_number=tag_number,
            verification_code=verification_code,
            photo_notes=f"Эмуляция сдачи (ADR-129): {text_notes}".strip(),
        )
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)
    if res.get("success"):
        mins = abs(res.get("time_applied_seconds", 0)) // 60
        xp = res.get("reward_xp", 0)
        await message.answer(
            f"🎉 **Испытание '{res.get('title')}' зачтено (эмуляция)!**\n\n"
            f"⏱ Сокращение таймера: **-{mins} мин**\n"
            f"💎 Начислено: **+{xp} XP**\n"
            f"🏷 Присвоен статус: `#obedient`",
            parse_mode="Markdown",
        )
    else:
        await message.answer(f"⚠️ Ошибка: {res.get('error')}", parse_mode="Markdown")

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.message(
    PersonalStates.waiting_for_wear_inspection_photo,
    F.photo,
)
@personal_router.message(
    PersonalStates.waiting_for_wear_inspection_tag,
    F.photo,
)
async def msg_wear_inspection_photo(message: types.Message, state: FSMContext):
    """Handles photo submission for seal tag inspection."""
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    photo = message.photo[-1]
    tag_from_caption = (message.caption or "").strip()

    async with async_session_factory() as db:
        session = await wear_svc.get_active_wear_session(db, user.id)
        tag_number = tag_from_caption or (session.current_tag_number if session else None) or "verified"
        await wear_svc.record_seal_inspection(
            db,
            user.id,
            tag_number=tag_number,
            notes=f"Фотоконтроль через Telegram (file_id: {photo.file_id})",
        )
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)
    await message.answer(
        f"🔍 **Фотоконтроль пломбы зарегистрирован!**\n"
        f"Пломба `#{tag_number}` проверена. Целостность пояса подтверждена.",
        parse_mode="Markdown",
    )

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)
