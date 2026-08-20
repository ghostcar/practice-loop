"""Telegram Bot Handlers for Public Tournaments, Ranks & D/s Status."""

from __future__ import annotations

import logging

from aiogram import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.community_agent import (
    CommunityMemberDelegation,
    CommunityTournament,
    CommunityTournamentEntry,
)
from app.models.user import User

logger = logging.getLogger(__name__)


async def get_user_by_chat_id(chat_id: int, db: AsyncSession | None = None) -> User | None:
    """Finds user by telegram chat ID."""
    if db is not None:
        res = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
        return res.scalar_one_or_none()

    async with async_session_factory() as db_sess:
        res = await db_sess.execute(select(User).where(User.telegram_chat_id == chat_id))
        return res.scalar_one_or_none()


async def handle_tournaments_command(message: types.Message, db: AsyncSession | None = None):
    """List active public community tournaments."""
    user = await get_user_by_chat_id(message.chat.id, db=db)
    if not user:
        await message.answer("⚠️ Аккаунт не привязан. Используйте /link <code>.")
        return

    if db is not None:
        tourneys_res = await db.execute(select(CommunityTournament).where(CommunityTournament.status == "active"))
        tourneys = tourneys_res.scalars().all()
    else:
        async with async_session_factory() as db_sess:
            tourneys_res = await db_sess.execute(
                select(CommunityTournament).where(CommunityTournament.status == "active")
            )
            tourneys = tourneys_res.scalars().all()

    if not tourneys:
        await message.answer("🏆 Активных публичных турниров сообщества сейчас нет.")
        return

    lines = ["🏆 *Активные Публичные Турниры Сообщества:*"]
    for t in tourneys:
        lines.append(f"• *{t.title}* ({t.metric_type})\n  _{t.description}_")

    await message.answer("\n\n".join(lines), parse_mode="Markdown")


async def handle_my_rank_command(message: types.Message, db: AsyncSession | None = None):
    """Show user rank in active community tournaments."""
    user = await get_user_by_chat_id(message.chat.id, db=db)
    if not user:
        await message.answer("⚠️ Аккаунт не привязан. Используйте /link <code>.")
        return

    if db is not None:
        entries_res = await db.execute(
            select(CommunityTournamentEntry).where(CommunityTournamentEntry.user_id == user.id)
        )
        entries = entries_res.scalars().all()
    else:
        async with async_session_factory() as db_sess:
            entries_res = await db_sess.execute(
                select(CommunityTournamentEntry).where(CommunityTournamentEntry.user_id == user.id)
            )
            entries = entries_res.scalars().all()

    if not entries:
        await message.answer("📊 Вы пока не участвуете ни в одном публичном турнире.")
        return

    lines = ["📊 *Ваши Позиции в Турнирах:*"]
    for e in entries:
        lines.append(f"• Ранг #{e.rank} — {e.points} очков")

    await message.answer("\n".join(lines), parse_mode="Markdown")


async def handle_ds_status_command(message: types.Message, db: AsyncSession | None = None):
    """Show D/s submissive delegation and compliance status."""
    user = await get_user_by_chat_id(message.chat.id, db=db)
    if not user:
        await message.answer("⚠️ Аккаунт не привязан. Используйте /link <code>.")
        return

    if db is not None:
        del_res = await db.execute(
            select(CommunityMemberDelegation).where(CommunityMemberDelegation.user_id == user.id)
        )
        delegation = del_res.scalar_one_or_none()
    else:
        async with async_session_factory() as db_sess:
            del_res = await db_sess.execute(
                select(CommunityMemberDelegation).where(CommunityMemberDelegation.user_id == user.id)
            )
            delegation = del_res.scalar_one_or_none()

    if not delegation:
        await message.answer("🔒 Ваш профиль не делегирован ИИ-Верхнему Сообщества.")
        return

    msg = (
        "🔒 *Статус D/s Подконтрольного*\n"
        f"• Compliance Score: *{delegation.compliance_score:.1f}%*\n"
        "• Делегированы: Задачи, Тренировки, Уход, Таймеры"
    )
    await message.answer(msg, parse_mode="Markdown")
