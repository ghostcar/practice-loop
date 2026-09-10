"""Personal Contour — Medications & Slot Intakes."""

from __future__ import annotations

import uuid

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import app.services.med_service as med_svc
from app.database import async_session_factory
from app.gamification.medication import on_medication_taken
from app.models.medication import Medication, MedKit, MedSchedule, MedStock
from app.telegram.keyboards import get_med_slot_keyboard
from app.telegram.pc.helpers import (
    _SCAN_CACHE,
    PersonalStates,
    _get_user_by_chat,
    _require_user,
    personal_router,
)
from app.timeutils import local_now, local_today


@personal_router.message(F.text.in_(["💊 Лекарства", "Лекарства", "/med", "/meds"]))
async def handle_medications_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    async with async_session_factory() as db:
        summary = await med_svc.schedule_summary(db, user_id=user.id)

    slots = summary.get("slots", [])
    pending_slots = [s for s in slots if s.get("pending")]

    lines = ["💊 *Приём лекарств на сегодня*"]
    total_doses = sum(len(s.get("meds", [])) for s in slots)
    taken_doses = sum(sum(1 for m in s.get("meds", []) if m.get("taken")) for s in slots)
    if total_doses > 0:
        lines.append(f"Прогресс: *{taken_doses}/{total_doses}* приёмов\n")

    if not pending_slots:
        lines.append("🎉 *Все лекарства на сегодня приняты! Отличная дисциплина.*")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📸 Сканировать пачку", callback_data="med_scan_guide")],
                [InlineKeyboardButton(text="📦 Мои аптечки", callback_data="med_kits_view")],
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="nav_meds")],
            ]
        )
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
        return

    first_slot = pending_slots[0]
    slot_time = first_slot.get("time", "Сегодня")
    slot_key = slot_time
    lines.append(f"⏰ *Ближайший слот:* **{slot_time}**")

    items = first_slot.get("meds", [])
    meal_groups = first_slot.get("meal_groups", [])

    if meal_groups:
        for mg in meal_groups:
            lines.append(f"\n🍽 *{mg['label']}:*")
            for it in mg.get("meds", []):
                status_icon = "✅" if it.get("taken") else "⏳"
                kit_note = f" _(📍 {it['preferred_kit_name']})_" if it.get("preferred_kit_name") else ""
                lines.append(f"  • {status_icon} *{it['medication_name']}* — {it.get('dose', '1 доза')}{kit_note}")
    else:
        for it in items:
            status_icon = "✅" if it.get("taken") else "⏳"
            food_lbl = it.get("food_relation_label", it.get("food_relation"))
            food_note = f" ({food_lbl})" if it.get("food_relation") else ""
            kit_note = f" _(📍 {it['preferred_kit_name']})_" if it.get("preferred_kit_name") else ""
            lines.append(f"• {status_icon} *{it['medication_name']}* — {it.get('dose', '1 доза')}{food_note}{kit_note}")

    if len(pending_slots) > 1:
        lines.append(f"\n_Ещё запланировано слотов: {len(pending_slots) - 1}_")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_med_slot_keyboard(slot_key, slot_time, individual_items=items),
    )


@personal_router.callback_query(F.data == "nav_meds")
async def cb_nav_meds(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await handle_medications_tab(callback.message, state)
    await callback.answer()


@personal_router.callback_query(F.data.startswith("med_slot_take:"))
async def cb_med_slot_take(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    _slot_key = parts[1]
    slot_time = parts[2]

    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    async with async_session_factory() as db:
        summary = await med_svc.schedule_summary(db, user_id=user.id)
        matching_slot = next((s for s in summary.get("slots", []) if s.get("time") == slot_time), None)
        if not matching_slot:
            await callback.answer("Слот не найден или уже отмечен.", show_alert=True)
            return

        schedule_ids = [
            uuid.UUID(it["schedule_id"])
            for it in matching_slot.get("meds", [])
            if not it.get("taken") and it.get("schedule_id")
        ]

        if not schedule_ids:
            await callback.answer("Все препараты этого слота уже приняты!", show_alert=True)
            return

        await med_svc.record_batch_intake(db, user_id=user.id, schedule_ids=schedule_ids, slot_time=slot_time)
        res_xp = await on_medication_taken(db, user.id, f"Слот {slot_time}", on_time=True)
        await db.commit()

    xp = res_xp.get("xp_earned", 15)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💊 К расписанию лекарств", callback_data="nav_meds")]]
    )
    await callback.message.edit_text(
        f"✅ Приём лекарств за **{slot_time}** выполнен!\n"
        f"Остатки в аптечках пересчитаны.\n"
        f"⭐ +{xp} XP за дисциплину приёма! 💊",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Принято! 💊")


@personal_router.callback_query(F.data.startswith("med_take:"))
async def cb_med_take_one(callback: types.CallbackQuery):
    sched_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    try:
        sched_id = uuid.UUID(sched_id_str)
    except ValueError:
        await callback.answer("Неверный ID.", show_alert=True)
        return

    async with async_session_factory() as db:
        sched = (
            await db.execute(
                select(MedSchedule)
                .options(selectinload(MedSchedule.medication), selectinload(MedSchedule.preferred_kit))
                .where(MedSchedule.id == sched_id)
            )
        ).scalar_one_or_none()
        if not sched:
            await callback.answer("Расписание не найдено.", show_alert=True)
            return

        dose_val = float(sched.dose_quantity) if sched.dose_quantity else 1.0
        today = local_today()

        stocks = (
            await db.execute(
                select(MedStock)
                .options(selectinload(MedStock.kit))
                .where(
                    MedStock.user_id == user.id,
                    MedStock.medication_id == sched.medication_id,
                    MedStock.quantity > 0,
                )
            )
        ).scalars().all()

        valid_stocks = [st for st in stocks if (st.expiry_date is None or st.expiry_date >= today)]
        pref_stock = sum(
            float(st.quantity) for st in valid_stocks
            if st.kit_id == sched.preferred_kit_id
        ) if sched.preferred_kit_id else 0.0

        has_pref = bool(sched.preferred_kit_id)
        # Если аптечка указана и в ней достаточно остатка — списываем строго из неё
        if has_pref and pref_stock >= dose_val:
            await med_svc.record_batch_intake(
                db, user_id=user.id, schedule_ids=[sched_id], slot_time="now", kit_id=sched.preferred_kit_id
            )
            name = sched.medication.name if sched.medication else "Препарат"
            kit_name = sched.preferred_kit.name if sched.preferred_kit else "аптечки"
            res_xp = await on_medication_taken(db, user.id, name, on_time=True)
            await db.commit()

            xp = res_xp.get("xp_earned", 10)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="💊 К расписанию", callback_data="nav_meds")]]
            )
            await callback.message.edit_text(
                f"✅ Препарат *{name}* принят.\n📦 Списано из аптечки «{kit_name}».\n⭐ +{xp} XP",
                parse_mode="Markdown",
                reply_markup=kb,
            )
            await callback.answer("Принято! 💊")
            return

        # Если аптечка не указана ИЛИ запас в ней исчерпан — спрашиваем пользователя (без слепого автосписания)
        name = sched.medication.name if sched.medication else "Препарат"
        stocks_by_kit: dict[str, tuple[str, float]] = {}
        for st in valid_stocks:
            kid = str(st.kit_id) if st.kit_id else "none"
            kname = st.kit.name if st.kit else "Основная аптечка"
            prev_name, prev_q = stocks_by_kit.get(kid, (kname, 0.0))
            stocks_by_kit[kid] = (kname, prev_q + float(st.quantity))

        rows = []
        for kid, (kname, kqty) in stocks_by_kit.items():
            if kqty > 0:
                rows.append([
                    InlineKeyboardButton(
                        text=f"📦 {kname} (ост. {kqty:g})",
                        callback_data=f"med_tk_kit:{sched_id}:{kid}",
                    )
                ])
        rows.append([
            InlineKeyboardButton(
                text="🚫 Принять без списания",
                callback_data=f"med_tk_kit:{sched_id}:none",
            )
        ])
        rows.append([
            InlineKeyboardButton(text="⬅️ Отмена", callback_data="nav_meds")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        reason = "Запас в назначенной аптечке исчерпан" if has_pref else "Аптечка не привязана к курсу"
        await callback.message.edit_text(
            f"💊 Приём: *{name}*\n"
            f"⚠️ {reason}. Откуда списываем остаток?",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        await callback.answer()


@personal_router.callback_query(F.data.startswith("med_tk_kit:"))
async def cb_med_take_with_chosen_kit(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    sched_id_str = parts[1]
    kit_id_str = parts[2]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    try:
        sched_id = uuid.UUID(sched_id_str)
        chosen_kit_id = uuid.UUID(kit_id_str) if kit_id_str != "none" else None
    except ValueError:
        await callback.answer("Неверные параметры.", show_alert=True)
        return

    async with async_session_factory() as db:
        sched = (
            await db.execute(
                select(MedSchedule)
                .options(selectinload(MedSchedule.medication))
                .where(MedSchedule.id == sched_id)
            )
        ).scalar_one_or_none()
        if not sched:
            await callback.answer("Расписание не найдено.", show_alert=True)
            return

        name = sched.medication.name if sched.medication else "Препарат"
        chosen_kit_name = None
        if chosen_kit_id:
            kit_obj = (
                await db.execute(select(MedKit).where(MedKit.id == chosen_kit_id))
            ).scalar_one_or_none()
            if kit_obj:
                chosen_kit_name = kit_obj.name

        await med_svc.record_intake(
            db,
            user_id=user.id,
            medication_id=sched.medication_id,
            schedule_id=sched.id,
            status="taken",
            taken_at=local_now().isoformat(),
            quantity_taken=float(sched.dose_quantity) if sched.dose_quantity else 1.0,
            kit_id=chosen_kit_id,
            deduct_stock=(chosen_kit_id is not None),
            gamification=True,
        )
        res_xp = await on_medication_taken(db, user.id, name, on_time=True)
        await db.commit()

    xp = res_xp.get("xp_earned", 10)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💊 К расписанию", callback_data="nav_meds")]]
    )
    if chosen_kit_name:
        deduct_msg = f"📦 Списано из аптечки «{chosen_kit_name}»."
    else:
        deduct_msg = "ℹ️ Зафиксировано без списания остатков."

    await callback.message.edit_text(
        f"✅ Препарат *{name}* принят.\n{deduct_msg}\n⭐ +{xp} XP",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Принято! 💊")


@personal_router.callback_query(F.data.startswith("med_snooze:"))
async def cb_med_snooze(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    minutes = parts[1]
    slot_time = parts[2] if len(parts) > 2 else ""
    await callback.answer(f"⏰ Отложено на {minutes} мин", show_alert=False)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💊 К расписанию", callback_data="nav_meds")]]
    )
    await callback.message.edit_text(
        f"⏰ Напоминание для слота **{slot_time}** отложено на **{minutes} минут**.\n"
        f"Примите лекарства, как только появится возможность!",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@personal_router.callback_query(F.data == "med_prn_select")
async def cb_med_prn_select(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    async with async_session_factory() as db:
        stocks = (
            await db.execute(
                select(MedStock)
                .join(Medication)
                .where(MedStock.user_id == user.id, MedStock.quantity > 0)
                .order_by(Medication.name)
            )
        ).scalars().all()

    if not stocks:
        await callback.answer("В аптечках нет доступных остатков лекарств.", show_alert=True)
        return

    meds_seen: dict[uuid.UUID, dict] = {}
    for st in stocks:
        if st.medication_id not in meds_seen:
            meds_seen[st.medication_id] = {
                "name": st.medication.name if st.medication else "Препарат",
                "unit": st.unit or "шт",
                "total": sum(s.quantity for s in stocks if s.medication_id == st.medication_id),
            }

    rows = []
    for mid, info in list(meds_seen.items())[:8]:
        rows.append([
            InlineKeyboardButton(
                text=f"💊 {info['name'][:24]} ({info['total']:g} {info['unit']})",
                callback_data=f"med_prn_med:{mid}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="nav_meds")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await callback.message.edit_text(
        "⚡ *Ситуативный приём по требованию (PRN)*\n\n"
        "Выберите препарат для внепланового приёма (например, обезболивающее или спазмолитик):",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer()


@personal_router.callback_query(F.data.startswith("med_prn_med:"))
async def cb_med_prn_med(callback: types.CallbackQuery):
    med_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    try:
        med_id = uuid.UUID(med_id_str)
    except ValueError:
        await callback.answer("Неверный ID.", show_alert=True)
        return

    async with async_session_factory() as db:
        stocks = (
            await db.execute(
                select(MedStock)
                .where(MedStock.user_id == user.id, MedStock.medication_id == med_id, MedStock.quantity > 0)
            )
        ).scalars().all()
        med = (await db.execute(select(Medication).where(Medication.id == med_id))).scalar_one_or_none()

    if not stocks or not med:
        await callback.answer("Препарат не найден в аптечках.", show_alert=True)
        return

    rows = []
    for st in stocks:
        kit_label = st.kit.name if st.kit else "Основная аптечка"
        rows.append([
            InlineKeyboardButton(
                text=f"📦 {kit_label}: списать 1 шт (ост. {st.quantity:g})",
                callback_data=f"med_prn_confirm:{med.id}:{st.kit_id or 'none'}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="nav_meds")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await callback.message.edit_text(
        f"⚡ Приём: *{med.name}*\n"
        f"Из какой аптечки списать остаток?",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer()


@personal_router.callback_query(F.data.startswith("med_prn_confirm:"))
async def cb_med_prn_confirm(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    med_id_str = parts[1]
    kit_id_str = parts[2]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    try:
        med_id = uuid.UUID(med_id_str)
        kit_id = uuid.UUID(kit_id_str) if kit_id_str != "none" else None
    except ValueError:
        await callback.answer("Ошибка параметров.", show_alert=True)
        return

    async with async_session_factory() as db:
        await med_svc.record_prn_intake(
            db,
            user_id=user.id,
            medication_id=med_id,
            quantity_taken=1.0,
            kit_id=kit_id,
            symptom_reason="Ситуативный приём через Telegram",
            gamification=True,
        )
        med = (await db.execute(select(Medication).where(Medication.id == med_id))).scalar_one_or_none()
        med_name = med.name if med else "Препарат"
        await db.commit()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💊 К расписанию", callback_data="nav_meds")]]
    )
    await callback.message.edit_text(
        f"⚡ *Ситуативный приём зарегистрирован!*\n\n"
        f"• Препарат: *{med_name}* (1 шт)\n"
        f"• Списано из остатков аптечки\n"
        f"• Журнал приёмов обновлён.",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Принято! 💊")


@personal_router.callback_query(F.data == "med_kits_view")
async def cb_med_kits_view(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        stmt = select(MedKit).where(MedKit.user_id == user.id).order_by(MedKit.name)
        kits = (await db.execute(stmt)).scalars().all()
        summary = await med_svc.schedule_summary(db, user.id)

    lines = ["📦 *Ваши аптечки и запасы*\n"]
    if not kits:
        lines.append("У вас пока нет созданных аптечек. Создайте их в веб-интерфейсе на сайте.")
    else:
        for k in kits:
            loc = f" 📍 {k.location_id}" if k.location_id else ""
            lines.append(f"• **{k.name}**{loc}")

    low = summary.get("low_stock", [])
    if low:
        lines.append("\n⚠️ *Заканчивающиеся препараты:*")
        for item in low[:4]:
            lines.append(f"• {item['medication_name']} — осталось {item['quantity']:g}")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 Сканировать DataMatrix", callback_data="med_scan_guide")],
            [InlineKeyboardButton(text="💊 Назад к лекарствам", callback_data="nav_meds")],
        ]
    )
    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@personal_router.callback_query(F.data == "med_scan_guide")
async def cb_med_scan_guide(callback: types.CallbackQuery):
    await callback.message.answer(
        "📸 *Сканирование маркировки (Честный Знак)*\n\n"
        "Просто отправьте фотографию квадратного DataMatrix-кода с упаковки препарата в этот чат.\n"
        "Бот автоматически считает серию, срок годности, GTIN и предложит добавить пачку в аптечку!",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.callback_query(F.data == "med_restock_list")
async def cb_med_restock_list(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        stmt = select(Medication).where(Medication.user_id == user.id).order_by(Medication.name)
        meds = (await db.execute(stmt)).scalars().all()

    if not meds:
        await callback.answer("В справочнике пока нет добавленных препаратов.", show_alert=True)
        return

    lines = ["📥 *Пополнение запаса медикаментов*\n", "Выберите препарат для добавления остатка:"]
    kb_rows = []
    for m in meds[:10]:
        kb_rows.append([InlineKeyboardButton(text=f"💊 {m.name}", callback_data=f"med_restock_sel:{m.id}")])
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="nav_meds")])

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )
    await callback.answer()


@personal_router.callback_query(F.data.startswith("med_restock_sel:"))
async def cb_med_restock_sel(callback: types.CallbackQuery, state: FSMContext):
    med_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    try:
        med_id = uuid.UUID(med_id_str)
    except ValueError:
        await callback.answer("Неверный ID.", show_alert=True)
        return

    async with async_session_factory() as db:
        stmt = select(Medication).where(Medication.id == med_id, Medication.user_id == user.id)
        med = (await db.execute(stmt)).scalar_one_or_none()

    if not med:
        await callback.answer("Препарат не найден.", show_alert=True)
        return

    await state.update_data(restock_med_id=str(med.id), restock_med_name=med.name, restock_med_unit=med.unit or "шт")
    await state.set_state(PersonalStates.waiting_for_med_restock_qty)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="nav_meds")]]
    )
    await callback.message.edit_text(
        f"📥 *Пополнение запаса: {med.name}*\n\n"
        f"Введите количество для добавления (например, `10`, `20`, `30` {med.unit or 'шт'}):",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_med_restock_qty)
async def msg_med_restock_qty(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.clear()
        return

    raw_text = (message.text or "").strip().replace(",", ".")
    try:
        qty = float(raw_text)
        if qty <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите положительное число (например: 10 или 20):")
        return

    data = await state.get_data()
    med_id_str = data.get("restock_med_id")
    med_name = data.get("restock_med_name", "Препарат")
    med_unit = data.get("restock_med_unit", "шт")
    await state.clear()

    if not med_id_str:
        await message.answer("Ошибка сессии пополнения. Попробуйте снова.")
        return

    med_id = uuid.UUID(med_id_str)
    async with async_session_factory() as db:
        stock = (
            await db.execute(
                select(MedStock).where(MedStock.user_id == user.id, MedStock.medication_id == med_id)
            )
        ).scalars().first()

        if stock:
            stock.quantity = float(stock.quantity or 0) + qty
            total_qty = stock.quantity
        else:
            stock = MedStock(
                user_id=user.id,
                medication_id=med_id,
                quantity=qty,
                unit=med_unit,
                notes="Пополнено через Telegram-бота",
            )
            db.add(stock)
            total_qty = qty
        await db.commit()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💊 К расписанию лекарств", callback_data="nav_meds")]]
    )
    await message.answer(
        f"✅ Запас препарата *{med_name}* успешно пополнен на *+{qty:g} {med_unit}*!\n"
        f"Текущий остаток: *{total_qty:g} {med_unit}*.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@personal_router.callback_query(F.data.startswith("dm_kit:"))
async def inline_datamatrix_add_to_kit(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Ошибка запроса.", show_alert=True)
        return

    scan_id = parts[1]
    try:
        kit_id = uuid.UUID(parts[2])
    except ValueError:
        await callback.answer("Неверный ID аптечки.", show_alert=True)
        return

    cached = _SCAN_CACHE.get(scan_id)
    if not cached:
        await callback.answer("Срок действия данных сканирования истёк.", show_alert=True)
        return

    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None or str(user.id) != cached["user_id"]:
        await callback.answer("Ошибка доступа.", show_alert=True)
        return

    async with async_session_factory() as db:
        stmt = select(MedKit).where(MedKit.id == kit_id, MedKit.user_id == user.id)
        kit = (await db.execute(stmt)).scalar_one_or_none()
        if not kit:
            await callback.answer("Аптечка не найдена.", show_alert=True)
            return

        med_id_str = cached.get("med_id")
        if med_id_str:
            med_id = uuid.UUID(med_id_str)
        else:
            notes = f"GTIN: {cached.get('gtin', '')}"
            new_med = await med_svc.create_medication(
                db,
                user_id=user.id,
                name=cached["med_name"],
                kind="medication",
                notes=notes,
            )
            med_id = new_med.id

        await med_svc.add_stock_to_kit(
            db,
            user_id=user.id,
            kit_id=kit_id,
            medication_id=med_id,
            quantity=1.0,
            expiry_date=cached.get("expiry") or "",
            lot_number=cached.get("lot") or "",
            notes="Добавлено через сканер DataMatrix",
        )
        await db.commit()

    _SCAN_CACHE.pop(scan_id, None)
    await callback.message.edit_text(
        f"✅ Препарат *{cached['med_name']}* успешно добавлен в аптечку *{kit.name}*!\n"
        f"📦 Партия: `{cached.get('lot') or '—'}`\n"
        f"📅 Срок годности: `{cached.get('expiry') or '—'}`",
        parse_mode="Markdown",
    )
    await callback.answer("Добавлено в аптечку! 💊")

