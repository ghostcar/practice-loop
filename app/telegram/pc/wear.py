"""Personal Contour — Chastity & Wear (ADR-195)."""

from __future__ import annotations

import contextlib
import uuid

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup

from app.database import async_session_factory
from app.models.user import User
from app.services import wear_reactive_service as wear_svc
from app.telegram.keyboards import (
    get_wear_card_keyboard,
    get_wear_comfort_keyboard,
    get_wear_device_selection_keyboard,
    get_wear_reasons_keyboard,
)
from app.telegram.pc.helpers import (
    PersonalStates,
    _get_user_by_chat,
    personal_router,
)


def _render_wear_card(
    status: dict,
    is_agent_mode: bool = False,
    user: User | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Renders the real-time wear status card with exact second timer and actions."""
    from app.services.identity_service import get_active_tags

    is_active = status.get("is_active", False)
    is_locked = status.get("is_locked", False)
    supports_tag = status.get("supports_tag", True)
    session = status.get("session")

    is_frozen = bool(session.is_frozen) if session else False
    extensions_state = dict(session.extensions_state or {}) if session else {}
    active_challenge = extensions_state.get("active_challenge")
    has_challenge = bool(active_challenge)
    bad_luck_streak = extensions_state.get("bad_luck_streak", 0)

    lines = ["🔒 **Пояс верности: Свободный режим**\n"]

    if user:
        tags = get_active_tags(user)
        if tags:
            tag_badges = " ".join([f"`{t}`" for t in tags[:8]])
            lines.append(f"🏷 **Статусы:** {tag_badges}")
            if "#pathetic_loser" in tags:
                lines.append("💀 **Позорное клеймо: Хронический неудачник (#pathetic_loser)**")

    if not is_active:
        lines.append("⚪️ **Текущее состояние: НЕ НАДЕТ (Свободен)**")
        lines.append("Активная сессия ношения пояса отсутствует.")
        lines.append("\n_Вы можете запереть пояс, выбрав устройство из инвентаря._")
    elif is_frozen:
        lines.append("❄️ **Текущее состояние: ЗАМОРОЖЕН**")
        lines.append(f"⏱ **{status['time_text']}**")
    elif is_locked:
        lines.append("🟢 **Текущее состояние: ЗАПЕРТ**")
        lines.append(f"⏱ **{status['time_text']}**")
    else:
        lines.append("🔴 **Текущее состояние: СНЯТ**")
        lines.append(f"⏱ **{status['time_text']}**")

    if bad_luck_streak >= 2:
        lines.append(
            f"\n⚠️ **Полоса неудач:** {bad_luck_streak} поражений подряд! При следующей неудаче статус усугубится."
        )

    if has_challenge and active_challenge:
        reward_mins = abs(active_challenge.get("reward_seconds", 0)) // 60
        reward_xp = active_challenge.get("reward_xp", 0)
        lines.append(
            f"\n🎭 **АКТИВНО ИСПЫТАНИЕ ПОСЛУШАНИЯ:**\n"
            f"• *{active_challenge.get('title')}*\n"
            f"• Код проверки: `{active_challenge.get('verification_code')}`\n"
            f"• Награда: -{reward_mins} мин к таймеру, +{reward_xp} XP\n"
            f"📸 _Отправьте фото с кодом прямо в чат или нажмите кнопку сдачи._"
        )

    if extensions_state.get("is_pilloried"):
        lines.append("\n⛓️ **ВЫ НА ПОЗОРНОМ СТОЛБЕ** (продление по голосам сообщества)")

    if is_active and not is_locked and status.get("deadline_text"):
        lines.append(f"\n{status['deadline_text']}")

    pending = status.get("pending_open")
    if is_active and not is_locked and pending:
        reason_label = pending.definition.title if pending.definition else pending.event_code
        lines.append(f"\n📋 **Причина снятия:** {reason_label}")
        if pending.user_comment:
            lines.append(f"💬 _{pending.user_comment}_")
        if pending.llm_analysis:
            lines.append(f"🤖 _{pending.llm_analysis}_")

    if is_active:
        lines.append("")
        device = status.get("device")
        if device:
            lines.append(f"🛡 **Устройство:** {device.name}")

        if supports_tag:
            tag = status.get("current_tag")
            lines.append(f"🏷 **Пломба / Бирка:** `#{tag}`" if tag else "🏷 **Пломба / Бирка:** _нет_")
        else:
            lines.append("🏷 **Пломба / Бирка:** _не предусмотрена конструкцией_")

        comfort = status.get("last_comfort")
        lines.append(f"⭐ **Комфорт:** {comfort}/5" if comfort else "⭐ **Комфорт:** _не оценён_")

    slots = status.get("upcoming_slots")
    if slots:
        lines.append("\n📅 **События базового таймера на сегодня:**")
        for s in slots:
            open_t = s["planned_open_at"].strftime("%H:%M")
            close_t = s["planned_close_at"].strftime("%H:%M") if s.get("planned_close_at") else "..."
            lines.append(f"• {open_t} – {close_t} ({s['state']})")

    keyboard = get_wear_card_keyboard(
        is_active=is_active,
        is_locked=is_locked,
        is_agent_mode=is_agent_mode,
        supports_tag=supports_tag,
        is_frozen=is_frozen,
        has_challenge=has_challenge,
    )
    return "\n".join(lines), keyboard


@personal_router.message(F.text.in_(["🔒 Пояс", "Пояс", "/wear", "/chastity", "/lock"]))
async def msg_wear_card(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await message.answer(
            "🔒 Для управления поясом привяжите аккаунт через /link `КОД`",
            parse_mode="Markdown",
        )
        return

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)

    async with async_session_factory() as db:
        status = await wear_svc.get_wear_status(db, user.id)

    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "wear_refresh")
async def cb_wear_refresh(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)

    async with async_session_factory() as db:
        status = await wear_svc.get_wear_status(db, user.id)

    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer("⏱ Таймер обновлён")


@personal_router.callback_query(F.data == "wear_toggle_agent")
async def cb_wear_toggle_agent(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cur_agent = data.get("wear_agent_mode", False)
    new_agent = not cur_agent
    await state.update_data(wear_agent_mode=new_agent)

    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        status = await wear_svc.get_wear_status(db, user.id)

    text, kb = _render_wear_card(status, is_agent_mode=new_agent, user=user)

    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    status_label = "включен (свободный ввод)" if new_agent else "выключен (кнопки выбора)"
    await callback.answer(f"🤖 Агентский режим {status_label}")


@personal_router.callback_query(F.data == "wear_start_init")
async def cb_wear_start_init(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        devices = await wear_svc.get_user_chastity_devices(db, user.id)

    if devices:
        kb = get_wear_device_selection_keyboard(devices)
        await callback.message.edit_text(
            "🔒 **Выбор пояса верности**\n\n"
            "Выберите пояс / устройство из вашего инвентаря для надевания:",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        await callback.answer()
        return

    await state.update_data(chosen_device_id=None)
    await state.set_state(PersonalStates.waiting_for_wear_start_tag)
    await callback.message.answer(
        "🔒 **Начало ношения пояса верности**\n\n"
        "Введите номер пломбы / бирки (или отправьте `-` если закрываете без номерной бирки):\n\n"
        "_Для отмены отправьте /cancel_",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.callback_query(F.data.startswith("wear_dev:"))
async def cb_wear_select_device(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    dev_code = callback.data.split(":", 1)[1]
    if dev_code == "none":
        await state.update_data(chosen_device_id=None)
        await state.set_state(PersonalStates.waiting_for_wear_start_tag)
        await callback.message.edit_text(
            "🔒 **Фиксация пломбы (без устройства из инвентаря)**\n\n"
            "Введите номер пломбы / бирки (или отправьте `-` если закрываете без номерной бирки):\n\n"
            "_Для отмены отправьте /cancel_",
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    try:
        dev_uuid = uuid.UUID(dev_code)
    except Exception:
        await callback.answer("Некорректный идентификатор устройства", show_alert=True)
        return

    async with async_session_factory() as db:
        device = await wear_svc.get_device_by_id(db, dev_uuid, user.id)
        if not device:
            await callback.answer("Устройство не найдено в инвентаре", show_alert=True)
            return

        supports_tag = wear_svc.device_supports_tag(device)

        if not supports_tag:
            session, initial_log = await wear_svc.start_open_ended_session(
                db,
                user.id,
                tag_number=None,
                device_id=device.id,
            )
            status = await wear_svc.get_wear_status(db, user.id)

            await state.set_state(None)
            await callback.message.edit_text(
                f"🔒 **Пояс надет и заперт!**\n\n"
                f"🛡 **Устройство:** {device.name}\n"
                f"🏷 **Пломба:** не требуется (конструкция без пломбирования)\n"
                f"⏱ Период ношения начался, таймер запущен.",
                parse_mode="Markdown",
            )
            data = await state.get_data()
            is_agent_mode = data.get("wear_agent_mode", False)
            text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
            await callback.answer()
            return

    await state.update_data(chosen_device_id=str(device.id))
    await state.set_state(PersonalStates.waiting_for_wear_start_tag)
    await callback.message.edit_text(
        f"🔒 **Фиксация пломбы для «{device.name}»**\n\n"
        "Введите номер пломбы / бирки (или отправьте `-` если закрываете без номерной бирки):\n\n"
        "_Для отмены отправьте /cancel_",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_wear_start_tag)
async def msg_wear_start_tag(message: types.Message, state: FSMContext):
    if message.text and message.text.strip().lower() in ("/cancel", "отмена"):
        await state.set_state(None)
        await message.answer("Начало ношения отменено.")
        return

    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    raw = (message.text or "").strip()
    tag_number = None if raw in ("-", "—", "") else raw

    data = await state.get_data()
    chosen_dev_str = data.get("chosen_device_id")
    device_id = uuid.UUID(chosen_dev_str) if chosen_dev_str else None

    async with async_session_factory() as db:
        session, initial_log = await wear_svc.start_open_ended_session(
            db,
            user.id,
            tag_number=tag_number,
            device_id=device_id,
        )
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)

    lines = ["🔒 **Пояс надет и заперт!**", "Период ношения начался, таймер запущен."]
    if status.get("device"):
        lines.append(f"🛡 **Устройство:** {status['device'].name}")
    if tag_number:
        lines.append(f"🏷 Зафиксирована пломба: `#{tag_number}`")

    await message.answer("\n".join(lines), parse_mode="Markdown")

    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "wear_finish_init")
async def cb_wear_finish_init(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        await wear_svc.finish_open_ended_session(db, user.id)
        status = await wear_svc.get_wear_status(db, user.id)

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)

    await callback.message.answer(
        "⏹ **Период ношения пояса завершён.** Сессия закрыта.",
        parse_mode="Markdown",
    )
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@personal_router.callback_query(F.data == "wear_unlock_init")
async def cb_wear_unlock_init(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)

    if is_agent_mode:
        await state.set_state(PersonalStates.waiting_for_wear_agent_reason)
        await callback.message.answer(
            "🤖 **Ключник слушает вас.**\n\n"
            "Опишите причину снятия пояса в свободной форме "
            "(например: _«Нужно быстро принять душ после пробежки»_ или _«Трёт и очень сильно болит»_):\n\n"
            "_Для отмены отправьте /cancel_",
            parse_mode="Markdown",
        )
        await callback.answer()
    else:
        await callback.message.edit_text(
            "🔓 **Выберите причину снятия пояса:**\n\n"
            "⏱ _Для каждой причины действует свой лимит времени. "
            "Опоздание с возвратом пояса даже на 1 секунду повлечет штраф!_",
            parse_mode="Markdown",
            reply_markup=get_wear_reasons_keyboard(),
        )
        await callback.answer()


@personal_router.callback_query(F.data.startswith("wear_reason:"))
async def cb_wear_reason_selected(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    reason_code = callback.data.split(":", 1)[1]

    async with async_session_factory() as db:
        log_entry, reactions = await wear_svc.record_unlock_event(db, user.id, reason_code)
        status = await wear_svc.get_wear_status(db, user.id)

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)

    ack_text = f"🔓 **Пояс снят.** Зафиксировано событие: `{reason_code}`."
    if reactions.get("sexual_journal_id"):
        ack_text += "\n❤️ Создана черновая запись в Сексуальном журнале."
    if reactions.get("penalty_applied"):
        ack_text += f"\n⚠️ Применен штраф: {reactions['penalty_applied']} баллов."

    await callback.message.answer(ack_text, parse_mode="Markdown")
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_wear_agent_reason)
async def msg_wear_agent_reason(message: types.Message, state: FSMContext):
    if message.text and message.text.strip().lower() in ("/cancel", "отмена"):
        await state.set_state(None)
        await message.answer("Снятие пояса отменено.")
        return

    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    user_text = message.text or ""
    await message.answer("🤖 _Анализирую запрос с Ключником..._", parse_mode="Markdown")

    from app.llm.pipeline import get_active_llm_config as _get_llm_config
    from app.llm.pipeline.keyholder import classify_wear_unlock_reason

    async with async_session_factory() as db:
        llm_config = await _get_llm_config(db, user.id)
        classified = await classify_wear_unlock_reason(user_text, llm_config, locale="ru")

        event_code = classified.get("event_code", "hygiene_quick")
        duration_mins = classified.get("duration_minutes", 10)
        keyholder_msg = classified.get("keyholder_message", "Запрос одобрен Ключником.")

        log_entry, reactions = await wear_svc.record_unlock_event(
            db,
            user.id,
            event_code=event_code,
            duration_minutes=duration_mins,
            user_comment=user_text,
            llm_analysis=keyholder_msg,
        )
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)

    resp_lines = [
        "🤖 **Вердикт Ключника:**\n",
        f"_{keyholder_msg}_\n",
        f"⏱ Установлен таймер: **{duration_mins} мин.**",
        "⚠️ _Помните: опоздание с возвратом пояса хотя бы на 1 секунду повлечет штраф!_",
    ]
    if reactions.get("sexual_journal_id"):
        resp_lines.append("❤️ Запись о близости добавлена в Сексуальный журнал.")

    await message.answer("\n".join(resp_lines), parse_mode="Markdown")

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", True)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "wear_relock_init")
async def cb_wear_relock_init(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        status = await wear_svc.get_wear_status(db, user.id)

    if not status.get("supports_tag", True):
        async with async_session_factory() as db:
            relock_log, reactions = await wear_svc.record_relock_event(
                db,
                user.id,
                tag_number=None,
            )
            status = await wear_svc.get_wear_status(db, user.id)

        lines = ["🔒 **Пояс успешно заперт!**"]
        lines.append("🏷 Устройство заперто без пломбы (не предусмотрено).")
        if reactions.get("delay_penalty"):
            dp = reactions["delay_penalty"]
            lines.append(
                f"\n⚠️ **ВНИМАНИЕ: Зафиксировано опоздание на {dp['formatted_overdue']}!**\n"
                f"Начислен штраф: **{dp['amount']} баллов**."
            )
        else:
            lines.append("✅ Возврат выполнен вовремя без опоздания.")

        await callback.message.answer("\n".join(lines), parse_mode="Markdown")

        data = await state.get_data()
        is_agent_mode = data.get("wear_agent_mode", False)
        text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        await callback.answer()
        return

    await state.set_state(PersonalStates.waiting_for_wear_relock_tag)
    await callback.message.answer(
        "🔒 **Закрытие пояса**\n\n"
        "Введите номер новой пломбы / бирки (или отправьте `-` если закрываете без номерной бирки):",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_wear_relock_tag)
async def msg_wear_relock_tag(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    raw = (message.text or "").strip()
    tag_number = None if raw in ("-", "—", "") else raw

    async with async_session_factory() as db:
        relock_log, reactions = await wear_svc.record_relock_event(
            db,
            user.id,
            tag_number=tag_number,
        )
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)

    lines = ["🔒 **Пояс успешно заперт!**"]
    if tag_number:
        lines.append(f"🏷 Зафиксирована пломба: `#{tag_number}`")

    if reactions.get("delay_penalty"):
        dp = reactions["delay_penalty"]
        lines.append(
            f"\n⚠️ **ВНИМАНИЕ: Зафиксировано опоздание на {dp['formatted_overdue']}!**\n"
            f"Начислен штраф: **{dp['amount']} баллов**."
        )
    else:
        lines.append("✅ Возврат выполнен вовремя без опоздания.")

    await message.answer("\n".join(lines), parse_mode="Markdown")

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "wear_inspect_init")
async def cb_wear_inspect_init(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        status = await wear_svc.get_wear_status(db, user.id)

    if not status.get("supports_tag", True):
        await callback.answer("Устройство используется без номерной бирки/пломбы", show_alert=True)
        return

    await state.set_state(PersonalStates.waiting_for_wear_inspection_tag)
    await callback.message.answer(
        "🔍 **Проверка пломбы / бирки (без снятия)**\n\n"
        "Пояс остаётся запертым. Введите фактический номер пломбы для подтверждения целостности:",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_wear_inspection_tag)
async def msg_wear_inspection_tag(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    tag_number = (message.text or "").strip()
    if not tag_number:
        tag_number = "verified"

    async with async_session_factory() as db:
        await wear_svc.record_seal_inspection(db, user.id, tag_number=tag_number)
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)
    await message.answer(
        f"✅ **Пломба `#{tag_number}` проверена и подтверждена!**\nПояс не снимался.",
        parse_mode="Markdown",
    )

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "wear_comfort_init")
async def cb_wear_comfort_init(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⭐ **Оцените физический комфорт ношения пояса:**\n\n"
        "1 — Сильный дискомфорт / боль\n"
        "3 — Терпимо / привычно\n"
        "5 — Идеально / не ощущается",
        parse_mode="Markdown",
        reply_markup=get_wear_comfort_keyboard(),
    )
    await callback.answer()


@personal_router.callback_query(F.data.startswith("wear_score:"))
async def cb_wear_score_selected(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    score = int(callback.data.split(":", 1)[1])

    async with async_session_factory() as db:
        session = await wear_svc.get_or_create_open_ended_session(db, user.id)
        session.last_comfort_score = score
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer(f"Комфорт отмечен: {score}/5")


@personal_router.callback_query(F.data == "wear_orgasm_init")
async def cb_wear_orgasm_init(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PersonalStates.waiting_for_wear_orgasm_notes)
    await callback.message.answer(
        "💥 **Отметка оргазма / эякуляции**\n\n"
        "Событие будет зафиксировано и внесено в Сексуальный журнал независимо от текущего статуса пояса.\n\n"
        "Введите краткий комментарий или отправьте `+` для быстрой отметки:",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_wear_orgasm_notes)
async def msg_wear_orgasm_notes(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    notes = (message.text or "").strip()
    if notes in ("+", "-", ""):
        notes = "Фиксация оргазма через таймер ношения"

    async with async_session_factory() as db:
        orgasm_log, reactions = await wear_svc.record_orgasm_event(
            db,
            user.id,
            orgasms_count=1,
            notes=notes,
        )
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)
    await message.answer(
        "💥 **Оргазм зафиксирован и внесен в Сексуальный журнал!**",
        parse_mode="Markdown",
    )

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode, user=user)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)
