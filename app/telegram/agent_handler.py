"""Telegram Agent Router — Direct Integration with PracticeLoop Agent (Step 51 / ADR-123)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import F, Router, types
from aiogram.filters import Command

from app.agent.core import run_practice_agent
from app.database import async_session_factory
from app.models.user import User

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

agent_tg_router = Router()


async def _get_linked_user(chat_id: int) -> User | None:
    from sqlalchemy import select

    async with async_session_factory() as db:
        res = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
        return res.scalar_one_or_none()


@agent_tg_router.message(Command("agent"))
async def handle_agent_command(message: types.Message) -> None:
    """/agent command to start interactive dialogue with PracticeLoop Agent."""
    user = await _get_linked_user(message.chat.id)
    if not user:
        await message.reply(
            "Ваш Telegram-аккаунт не привязан к PracticeLoop. Зайдите в Профиль на сайте и введите код связывания."
        )
        return

    await message.reply(
        "🤖 **PracticeLoop Autonomous Agent** на связи!\n\n"
        "Вы можете отправлять мне текстовые вопросы, команды управления сессиями, "
        "или присылать фотографии выполнений практик для мультимодальной ИИ-верификации."
    )


@agent_tg_router.message(F.text & ~F.text.startswith("/"))
async def handle_agent_text_message(message: types.Message) -> None:
    """Passes any direct text message to PracticeLoop Agent ReAct Loop."""
    user = await _get_linked_user(message.chat.id)
    if not user:
        return  # Let other generic handlers process unlinked chats

    user_text = message.text or ""
    if not user_text.strip():
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    async with async_session_factory() as db:
        res = await run_practice_agent(
            user_prompt=user_text,
            user_id=user.id,
            db=db,
            persona_role="keyholder",
        )

    reply_text = res.get("reply", "Запрос обработан ИИ-Ассистентом.")
    tools_used = res.get("tool_calls", [])

    if tools_used:
        tool_names = ", ".join([t.get("tool", "tool") for t in tools_used])
        reply_text += f"\n\n🛠️ *Использованы инструменты:* `{tool_names}`"

    await message.reply(reply_text, parse_mode="Markdown")


@agent_tg_router.message(F.photo)
async def handle_agent_photo_verification(message: types.Message) -> None:
    """Passes photo submissions to PracticeLoop Agent Vision Verification Engine."""
    user = await _get_linked_user(message.chat.id)
    if not user:
        return

    caption = message.caption or "Физическое задание / Чек-ин замка"
    await message.reply("📸 Фото получено! ИИ-Ассистент проводит мультимодальную верификацию...")

    async with async_session_factory() as db:
        prompt = f"Мультимодальная верификация фото. Подпись к фото: {caption}"
        res = await run_practice_agent(
            user_prompt=prompt,
            user_id=user.id,
            db=db,
            persona_role="controller",
        )

    reply_text = res.get("reply", "Фото проанализировано.")
    await message.reply(reply_text)
