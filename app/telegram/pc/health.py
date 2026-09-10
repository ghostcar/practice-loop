"""Personal Contour — Health Check-in, Cycle, Body Measurements."""

from __future__ import annotations

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database import async_session_factory
from app.models.health import HealthState
from app.models.life import BodyMeasurement
from app.services.health_service import get_cycle_context
from app.telegram.keyboards import get_health_keyboard
from app.telegram.pc.helpers import (
    PersonalStates,
    _get_user_by_chat,
    _require_user,
    personal_router,
)
from app.timeutils import local_today


@personal_router.message(F.text.in_(["❤️ Чек-ин / Замеры", "Чек-ин / Замеры", "/health", "/checkin", "/cycle"]))
async def handle_health_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    today = local_today()
    async with async_session_factory() as db:
        state_row = (
            await db.execute(
                select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == today)
            )
        ).scalar_one_or_none()
        cycle = await get_cycle_context(db, user.id)
        latest_meas = (
            await db.execute(
                select(BodyMeasurement)
                .where(BodyMeasurement.user_id == user.id)
                .order_by(BodyMeasurement.measured_date.desc(), BodyMeasurement.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    lines = ["❤️ *Дневной чек-ин и показатели тела*"]
    mood_val = state_row.mood if state_row else None
    energy_val = state_row.energy if state_row else None

    lines.append(f"⭐ Настроение: *{'⭐' * mood_val if mood_val else 'не отмечено'}*")
    lines.append(f"⚡ Энергия: *{'⚡' * energy_val if energy_val else 'не отмечено'}*")

    if latest_meas and latest_meas.weight:
        lines.append(f"⚖️ Текущий вес: *{latest_meas.weight:g}* кг (от {latest_meas.measured_date.strftime('%d.%m')})")
    else:
        lines.append("⚖️ Вес: _ещё не записан_")

    if cycle.get("phase"):
        lines.append(f"🌸 Фаза цикла: *{cycle['phase']}* (день {cycle['day_of_cycle']})")

    lines.append("\n_Отметьте самочувствие шкалой ниже или запишите вес:_")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_health_keyboard(mood=mood_val, energy=energy_val),
    )


@personal_router.callback_query(F.data.startswith("health_mood:"))
async def cb_health_mood(callback: types.CallbackQuery):
    val = int(callback.data.split(":", 1)[1])
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    today = local_today()
    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == today)
            )
        ).scalar_one_or_none()
        if not row:
            row = HealthState(user_id=user.id, event_date=today)
            db.add(row)
        row.mood = val
        await db.commit()

    await callback.answer(f"Настроение сохранено: {val}/5 ⭐")


@personal_router.callback_query(F.data.startswith("health_energy:"))
async def cb_health_energy(callback: types.CallbackQuery):
    val = int(callback.data.split(":", 1)[1])
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    today = local_today()
    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == today)
            )
        ).scalar_one_or_none()
        if not row:
            row = HealthState(user_id=user.id, event_date=today)
            db.add(row)
        row.energy = val
        await db.commit()

    await callback.answer(f"Энергия сохранена: {val}/5 ⚡")


@personal_router.callback_query(F.data == "health_weight_prompt")
async def cb_health_weight_prompt(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PersonalStates.waiting_for_weight)
    await callback.message.answer(
        "⚖️ **Запись веса**\n\nОтправьте ваш текущий вес в килограммах (например: `72.5`):"
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_weight)
async def process_weight_input(message: types.Message, state: FSMContext):
    user = await _require_user(message)
    if user is None:
        await state.clear()
        return

    raw = (message.text or "").strip().replace(",", ".")
    try:
        weight_val = float(raw)
        if weight_val < 20 or weight_val > 350:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите корректное число для веса от 20 до 350 (например: `72.5`).")
        return

    today = local_today()
    async with async_session_factory() as db:
        meas = (
            await db.execute(
                select(BodyMeasurement).where(
                    BodyMeasurement.user_id == user.id,
                    BodyMeasurement.measured_date == today,
                    BodyMeasurement.time_of_day == "morning",
                )
            )
        ).scalar_one_or_none()

        if not meas:
            meas = BodyMeasurement(
                user_id=user.id,
                measured_date=today,
                time_of_day="morning",
                weight=weight_val,
            )
            db.add(meas)
        else:
            meas.weight = weight_val

        await db.commit()

    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❤️ К дневнику здоровья", callback_data="nav_health")]]
    )
    await message.answer(
        f"✅ Вес *{weight_val:g}* кг успешно записан на {today.strftime('%d.%m.%Y')}! ⚖️",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@personal_router.callback_query(F.data == "nav_health")
async def cb_nav_health(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await handle_health_tab(callback.message, state)
    await callback.answer()


@personal_router.callback_query(F.data == "health_cycle_view")
async def cb_health_cycle_view(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        cycle = await get_cycle_context(db, user.id)

    if not cycle.get("phase"):
        await callback.answer("Данные цикла не настроены на сайте.", show_alert=True)
        return

    lines = [
        "🌸 *Женский цикл*",
        f"Фаза: *{cycle.get('phase', '—')}*",
        f"День цикла: *{cycle.get('day_of_cycle', '—')}*",
    ]
    if cycle.get("next_period"):
        lines.append(f"Следующий период (расчёт): *{cycle['next_period']}*")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❤️ Назад", callback_data="nav_health")]]
    )
    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@personal_router.callback_query(F.data == "health_care_view")
async def cb_health_care_view(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❤️ Назад", callback_data="nav_health")]]
    )
    await callback.message.edit_text(
        "🧴 *Уход и процедуры*\n\n"
        "Для просмотра текущих курсов ухода и протоколов используйте команду `/care` "
        "или перейдите в веб-интерфейс раздела Care.",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer()
