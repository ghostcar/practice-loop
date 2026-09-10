"""Personal Contour — Navigation & Root Menu."""

from __future__ import annotations

from aiogram import types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.database import async_session_factory
from app.models.user import User
from app.telegram.keyboards import get_main_reply_keyboard
from app.telegram.pc.helpers import (
    _get_user_by_chat,
    _require_user,
    _try_link_by_code,
    personal_router,
)


async def _send_welcome_menu(message: types.Message, user: User) -> None:
    name = user.display_name or user.email.split("@")[0]
    text = (
        f"👋 Рады видеть вас, **{name}**!\n\n"
        "📱 **Персональный контур PracticeLoop активен.**\n"
        "Используйте постоянное меню снизу для быстрого доступа:\n\n"
        "• 📋 **План дня** — задачи на сегодня и отметка выполнения в 1 клик\n"
        "• 💊 **Лекарства** — приём по слотам и сканер пачек\n"
        "• 🤖 **AI-генератор** — умный подбор практик через ИИ\n"
        "• 🏋️ **Тренировка** — программа на день и упражнения\n"
        "• ❤️ **Чек-ин / Замеры** — самочувствие, вес и цикл\n"
        "• 🏆 **Прогресс** — опыт, серия дней и отработка штрафов\n\n"
        "💬 _Вы также можете просто написать мне любой вопрос или пожелание к практике текстом или голосом._"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_reply_keyboard())


@personal_router.message(Command("start"))
async def cmd_start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        linked = await _try_link_by_code(message, parts[1])
        if linked:
            return

    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await _require_user(message)
        return

    await _send_welcome_menu(message, user)


@personal_router.message(Command("menu"))
async def cmd_personal_menu(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return
    await _send_welcome_menu(message, user)


@personal_router.message(Command("link"))
async def cmd_link_handler(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Формат: `/link ВАШ_КОД`\n"
            "Код привязки можно скопировать в вашем профиле на портале.",
            parse_mode="Markdown",
        )
        return
    linked = await _try_link_by_code(message, parts[1])
    if not linked:
        await message.answer(
            "❌ Неверный или устаревший код привязки.\n"
            "Сгенерируйте свежий код в веб-профиле или отправьте команду `/connect` для получения OTP-кода."
        )


@personal_router.message(Command("connect"))
@personal_router.message(Command("otp"))
async def cmd_connect_otp_handler(message: types.Message):
    user = await _get_user_by_chat(message.chat.id)
    if user is not None:
        await message.answer(
            f"ℹ️ Ваш Telegram уже привязан к аккаунту **{user.email}**.\n"
            "Чтобы отвязать его, отправьте команду `/unlink`.",
            parse_mode="Markdown",
        )
        return

    from app.services.telegram_link_service import create_bot_connect_code

    otp = create_bot_connect_code(
        chat_id=message.chat.id,
        username=message.from_user.username if message.from_user else None,
        first_name=message.from_user.first_name if message.from_user else None,
        ttl_minutes=10,
    )
    text = (
        "🔑 **Ваш одноразовый код (OTP) для портала:**\n\n"
        f"`{otp}`\n"
        "_(нажмите на код выше, чтобы скопировать)_\n\n"
        "⏱ Код действует 10 минут.\n"
        "Откройте на сайте **Профиль → Telegram**, введите эти 6 цифр в поле ввода и нажмите **«Привязать»**."
    )
    await message.answer(text, parse_mode="Markdown")


@personal_router.message(Command("unlink"))
async def cmd_unlink_handler(message: types.Message):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await message.answer("Ваш Telegram-аккаунт не привязан ни к одному профилю.")
        return

    from app.services.telegram_link_service import unlink_user_telegram

    async with async_session_factory() as db:
        await unlink_user_telegram(db, user)
        await db.commit()

    await message.answer(
        "ℹ️ Ваш Telegram-аккаунт успешно отвязан от портала PracticeLoop.",
        reply_markup=types.ReplyKeyboardRemove(),
    )
