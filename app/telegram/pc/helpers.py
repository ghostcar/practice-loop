"""Personal Contour — shared helpers, states, router."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from aiogram import Router, types
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.user import User
from app.services.identity_registry import DEFAULT_STATUS_TAGS
from app.timeutils import as_utc

logger = logging.getLogger(__name__)

personal_router = Router(name="personal_contour")
_SCAN_CACHE: dict[str, dict[str, Any]] = {}

TAG_TITLES_RU: dict[str, str] = {
    item["tag"]: item["title_ru"]
    for cat in DEFAULT_STATUS_TAGS.values()
    for item in cat
}


class PersonalStates(StatesGroup):
    waiting_for_weight = State()
    waiting_for_custom_duration = State()
    waiting_for_wear_start_tag = State()
    waiting_for_wear_agent_reason = State()
    waiting_for_wear_relock_tag = State()
    waiting_for_wear_inspection_tag = State()
    waiting_for_wear_inspection_photo = State()
    waiting_for_challenge_photo = State()
    waiting_for_wear_orgasm_notes = State()
    waiting_for_med_restock_qty = State()
    waiting_for_seals_count = State()
    waiting_for_item_name = State()
    waiting_for_pillory_repentance_photo = State()


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _get_user_by_chat(chat_id: int) -> User | None:
    async with async_session_factory() as db:
        res = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
        return res.scalar_one_or_none()


async def _try_link_by_code(message: types.Message, raw_code: str, db: AsyncSession | None = None) -> bool:
    from app.telegram.keyboards import get_main_reply_keyboard

    code = raw_code.strip()
    if code.lower().startswith("link_"):
        code = code[5:]
    if not code:
        return False

    clean_code = code.upper()

    async def _do_linking(session: AsyncSession) -> bool:
        from app.models.ds_suite import ManagedSubmissive

        res = await session.execute(select(User).where(User.telegram_link_code == clean_code))
        user = res.scalar_one_or_none()
        if user:
            if user.telegram_link_code_expires and as_utc(user.telegram_link_code_expires) < datetime.now(UTC):
                await message.answer("⏰ Срок действия кода привязки истёк. Сгенерируйте новый код в профиле на сайте.")
                return True

            user.telegram_chat_id = message.chat.id
            user.telegram_link_code = None
            user.telegram_link_code_expires = None
            session.add(user)
            await session.commit()

            name = user.display_name or user.email.split("@")[0]
            await message.answer(
                f"🎉 **Аккаунт успешно привязан!**\n\n"
                f"Добро пожаловать, **{name}**!\n"
                "Персональный контур и главное меню активированы.",
                parse_mode="Markdown",
                reply_markup=get_main_reply_keyboard(),
            )
            return True

        sub_stmt = select(ManagedSubmissive).where(ManagedSubmissive.telegram_link_code == clean_code)
        sub_profile = (await session.execute(sub_stmt)).scalar_one_or_none()
        if sub_profile:
            exp = sub_profile.telegram_link_code_expires
            if exp and as_utc(exp) < datetime.now(UTC):
                await message.answer("⏰ Срок действия кода истёк. Запросите новый код у Ключника.")
                return True

            sub_profile.telegram_chat_id = str(message.chat.id)
            sub_profile.telegram_link_code = None
            sub_profile.telegram_link_code_expires = None
            session.add(sub_profile)
            await session.commit()

            await message.answer(
                f"👑 **D/s профиль привязан!** Добро пожаловать, **{sub_profile.name}**!\n\n"
                "Уведомления и задачи от Ключника подключены.",
                parse_mode="Markdown",
            )
            return True

        return False

    if db is not None:
        return await _do_linking(db)

    async with async_session_factory() as session:
        return await _do_linking(session)


async def _require_user(message: types.Message) -> User | None:
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await message.answer(
            "👋 **Ваш Telegram ещё не привязан к аккаунту PracticeLoop.**\n\n"
            "Выберите удобный способ привязки:\n"
            "1. **В 1 клик:** нажмите кнопку «Подключить Telegram» в вашем профиле на сайте.\n"
            "2. **Код из бота:** отправьте команду `/connect` — бот выдаст 6-значный OTP для ввода на сайте.\n"
            "3. **Код с сайта:** отправьте сюда команду `/link ВАШ_КОД`.",
            parse_mode="Markdown",
        )
        return None
    return user


def _progress_bar(current: int, total: int, length: int = 8) -> str:
    if total <= 0:
        return "░" * length
    filled = min(length, int((current / total) * length))
    return "█" * filled + "░" * (length - filled)
